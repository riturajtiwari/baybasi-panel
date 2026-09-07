"""A software DDP sink: pretend to be all four controllers, draw what arrives.

This exists so the driver and the upload utility can be written, demonstrated
and debugged before a single board is fabricated, and so that a mapping bug is
something you look at on a screen rather than something you infer from eight
feet of LEDs.

It is deliberately strict.  It reassembles frames the way the firmware will,
drops torn frames the way the firmware will, and complains about anything the
W5500 or the real controller would choke on:

* a UDP payload over 1472 bytes
* PUSH set on a data packet, which would latch the columns one at a time
* a write past the end of a controller's 9216-byte buffer
* a PUSH arriving with a controller only partly written

Demultiplexing: with ``network.id_mode: per_controller`` each column carries
its own DDP destination id, so one socket on one host can stand in for four
boards on four addresses.  With ``id_mode: default`` the sink falls back to the
source IP, which is what a real deployment looks like.
"""

from __future__ import annotations

import io
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from . import ddp
from .geometry import Controller, Wall
from .pixels import unpack


@dataclass
class ControllerState:
    ctrl: Controller
    buf: bytearray
    written: np.ndarray                      # per-byte coverage since the last PUSH
    packets: int = 0
    bytes_in: int = 0
    last_seq: Optional[int] = None
    seq_gaps: int = 0
    last_packet_t: float = 0.0
    complete_frames: int = 0
    torn_frames: int = 0

    @classmethod
    def make(cls, ctrl: Controller) -> "ControllerState":
        return cls(
            ctrl=ctrl,
            buf=bytearray(ctrl.n_bytes),
            written=np.zeros(ctrl.n_bytes, dtype=bool),
        )

    @property
    def coverage(self) -> float:
        return float(self.written.mean()) if self.written.size else 0.0

    @property
    def complete(self) -> bool:
        return bool(self.written.all())

    def reset_coverage(self) -> None:
        self.written[:] = False


@dataclass
class SinkStats:
    started: float = field(default_factory=time.monotonic)
    packets: int = 0
    bytes_in: int = 0
    pushes: int = 0
    frames: int = 0
    torn: int = 0
    violations: int = 0
    unattributed: int = 0
    render_skipped: int = 0
    last_frame_t: float = 0.0
    fps: float = 0.0
    recent: List[float] = field(default_factory=list)

    def note_frame(self, t: float) -> None:
        self.frames += 1
        self.last_frame_t = t
        self.recent.append(t)
        if len(self.recent) > 90:
            del self.recent[: len(self.recent) - 90]
        if len(self.recent) >= 2:
            span = self.recent[-1] - self.recent[0]
            self.fps = (len(self.recent) - 1) / span if span > 0 else 0.0



class FrameDispatcher(threading.Thread):
    """Hands frames to a renderer without ever blocking the receive path.

    A sink that writes PNGs, or draws to a terminal, is far slower than the
    wire.  If rendering ran on the receive thread the kernel socket buffer
    would overflow and the sink would report the driver as tearing when the
    only thing at fault was the sink.  So the newest frame goes in a one-slot
    mailbox and stale frames are dropped and *counted*, which is honest.
    """

    def __init__(self, callback):
        super().__init__(daemon=True, name="sink-render")
        self.callback = callback
        self._frame = None
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self.skipped = 0
        self.rendered = 0

    def submit(self, frame) -> None:
        with self._cv:
            if self._frame is not None:
                self.skipped += 1
            self._frame = frame
            self._cv.notify()

    def run(self) -> None:
        while not self._stop.is_set():
            with self._cv:
                while self._frame is None and not self._stop.is_set():
                    self._cv.wait(0.25)
                frame, self._frame = self._frame, None
            if frame is None:
                continue
            try:
                self.callback(frame)
            except Exception:  # a broken renderer must not stop the sink
                logging.getLogger("baybasi.sink").exception("renderer failed")
            self.rendered += 1

    def idle(self, timeout: float = 2.0) -> bool:
        """Wait until the mailbox is empty. For tests and clean shutdown."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self._cv:
                if self._frame is None:
                    return True
            time.sleep(0.005)
        return False

    def stop(self) -> None:
        self._stop.set()
        with self._cv:
            self._cv.notify_all()


class DDPSink:
    """Reassembles DDP frames.  Feed it packets; it hands you complete frames."""

    def __init__(
        self,
        wall: Wall,
        *,
        strict: bool = True,
        on_frame: Optional[Callable[[np.ndarray], None]] = None,
        on_violation: Optional[Callable[[str], None]] = None,
    ):
        self.wall = wall
        self.strict = strict
        self.on_violation = on_violation
        self.stats = SinkStats()
        self._dispatcher: Optional[FrameDispatcher] = None
        self.on_frame = on_frame
        self.states: Dict[int, ControllerState] = {
            c.column: ControllerState.make(c) for c in wall.controllers
        }
        self._by_id = {c.ddp_id: c.column for c in wall.controllers}
        self._by_ip = {c.ip: c.column for c in wall.controllers}
        self.frame = np.zeros((wall.height, wall.width, 3), dtype=np.uint8)
        self.frame_seq = 0
        self.lock = threading.Lock()
        self._warned: set = set()
        # A standing diagnosis is not a log line.  "Two senders are fighting"
        # stays true until you fix it, and must not scroll away underneath the
        # hundreds of torn-frame messages it is the cause of.
        self.notes: Dict[str, str] = {}
        self._torn_logged = 0.0
        self._torn_since_log = 0

    @property
    def on_frame(self):
        return self._on_frame

    @on_frame.setter
    def on_frame(self, cb) -> None:
        """Rendering always runs on its own thread; see FrameDispatcher."""
        self._on_frame = cb
        if self._dispatcher is not None:
            self._dispatcher.stop()
            self._dispatcher = None
        if cb is not None:
            self._dispatcher = FrameDispatcher(cb)
            self._dispatcher.start()

    def flush(self, timeout: float = 2.0) -> bool:
        return self._dispatcher.idle(timeout) if self._dispatcher else True

    def close(self) -> None:
        if self._dispatcher:
            self._dispatcher.stop()
            self._dispatcher = None

    # ---- reporting -----------------------------------------------------

    def _violation(self, msg: str) -> None:
        self.stats.violations += 1
        if self.on_violation:
            self.on_violation(msg)

    def _warn_once(self, key: str, msg: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self._violation(msg)

    def _note(self, key: str, msg: str) -> None:
        """Raise or refresh a standing diagnosis.

        The text carries live counters, so it changes on every call; it is
        logged once, on first appearance, and refreshed silently after that.
        """
        first = key not in self.notes
        self.notes[key] = msg
        if first and self.on_violation:
            self.on_violation(msg)

    # ---- packet path ---------------------------------------------------

    def resolve(self, hdr: ddp.DDPHeader, src_ip: Optional[str]) -> Optional[int]:
        """Which column does this packet belong to?"""
        col = self._by_id.get(hdr.dest_id)
        if col is not None:
            return col
        if src_ip is not None:
            col = self._by_ip.get(src_ip)
            if col is not None:
                return col
        if hdr.dest_id in (ddp.ID_DEFAULT_OUTPUT, ddp.ID_ALL) and len(self.states) == 1:
            return next(iter(self.states))
        return None

    def feed(self, raw: bytes, src_ip: Optional[str] = None) -> None:
        self.stats.packets += 1
        self.stats.bytes_in += len(raw)

        if len(raw) > ddp.MAX_UDP_PAYLOAD:
            self._violation(
                f"payload {len(raw)} B exceeds the {ddp.MAX_UDP_PAYLOAD} B limit; "
                "the W5500 does not fragment IP and would drop this"
            )

        try:
            pkt = ddp.parse_packet(raw)
        except ddp.DDPError as exc:
            self._violation(f"bad packet from {src_ip or '?'}: {exc}")
            return

        hdr = pkt.header
        if pkt.truncated:
            self._violation(
                f"header claims {hdr.length} B but only {len(pkt.data)} B arrived"
            )

        # A zero-length PUSH is the latch.  Anything else with PUSH set is the
        # per-controller latching that tears at the column seams.
        if hdr.push:
            if hdr.length:
                self._violation(
                    f"PUSH set on a {hdr.length}-byte data packet (id={hdr.dest_id}); "
                    "this latches one controller early and tears at the seam"
                )
            self._latch()
            if not hdr.length:
                return

        if not hdr.length:
            return

        col = self.resolve(hdr, src_ip)
        if col is None:
            self.stats.unattributed += 1
            self._warn_once(
                f"unattributed:{hdr.dest_id}:{src_ip}",
                f"cannot attribute packets with dest_id={hdr.dest_id} from "
                f"{src_ip or '?'} to a controller; check network.id_mode",
            )
            return

        st = self.states[col]
        end = hdr.offset + hdr.length
        if end > len(st.buf):
            self._violation(
                f"column {col}: write [{hdr.offset}:{end}) runs past the "
                f"{len(st.buf)}-byte buffer"
            )
            return

        st.buf[hdr.offset : end] = pkt.data[: hdr.length]
        st.written[hdr.offset : end] = True
        st.packets += 1
        st.bytes_in += hdr.length
        st.last_packet_t = time.monotonic()

        if hdr.sequence:
            if st.last_seq is not None:
                expected = st.last_seq % 15 + 1
                if hdr.sequence not in (st.last_seq, expected):
                    st.seq_gaps += 1
            st.last_seq = hdr.sequence

    # ---- latch ---------------------------------------------------------

    def _latch(self) -> None:
        now = time.monotonic()
        self.stats.pushes += 1

        touched = [st for st in self.states.values() if st.written.any()]
        if not touched:
            return

        incomplete = [st for st in touched if not st.complete]
        if incomplete and self.strict:
            for st in incomplete:
                st.torn_frames += 1
            self.stats.torn += 1
            names = ", ".join(
                f"col {st.ctrl.column} {st.coverage * 100:.0f}%" for st in incomplete
            )
            # One line a second, with a count.  A hundred identical messages
            # push the useful ones off the top of the box.
            self.stats.violations += 1
            self._torn_since_log += 1
            if now - self._torn_logged >= 1.0:
                extra = (f" (+{self._torn_since_log - 1} more)"
                         if self._torn_since_log > 1 else "")
                if self.on_violation:
                    self.on_violation(f"torn frame dropped: {names}{extra}")
                self._torn_logged = now
                self._torn_since_log = 0
            self._check_for_second_sender()
            for st in touched:
                st.reset_coverage()
            return

        with self.lock:
            for st in touched:
                unpack(bytes(st.buf), st.ctrl, self.wall, self.frame)
                st.complete_frames += 1
                st.reset_coverage()
            self.frame_seq += 1
            frame = self.frame.copy()

        self.stats.note_frame(now)
        if self._dispatcher is not None:
            self._dispatcher.submit(frame)
            self.stats.render_skipped = self._dispatcher.skipped

    def _check_for_second_sender(self) -> None:
        """The commonest cause of constant tearing on the bench, by far.

        Two senders on udp/4048 - a `baybasi pattern` left running alongside a
        driver, or two drivers - interleave their packets, so each PUSH lands
        on a part-written buffer.  Their sequence numbers cycle independently,
        which is what gives it away: one sender produces almost no gaps.
        """
        gaps = sum(st.seq_gaps for st in self.states.values())
        packets = sum(st.packets for st in self.states.values())
        if packets < 200 or gaps < packets * 0.05:
            return
        self._note(
            "two-senders",
            f"More than one sender is transmitting on "
            f"udp/{self.wall.network.ddp_port} ({gaps} sequence gaps in "
            f"{packets} packets). Stop any `baybasi pattern` or second "
            f"`baybasi driver` still running - that is what is tearing.",
        )

    # ---- summary -------------------------------------------------------

    def status(self) -> dict:
        return {
            "frames": self.stats.frames,
            "fps": round(self.stats.fps, 2),
            "packets": self.stats.packets,
            "bytes": self.stats.bytes_in,
            "pushes": self.stats.pushes,
            "torn": self.stats.torn,
            "violations": self.stats.violations,
            "unattributed": self.stats.unattributed,
            "render_skipped": self.stats.render_skipped,
            "notes": list(self.notes.values()),
            "controllers": [
                {
                    "column": st.ctrl.column,
                    "ip": st.ctrl.ip,
                    "ddp_id": st.ctrl.ddp_id,
                    "packets": st.packets,
                    "bytes": st.bytes_in,
                    "frames": st.complete_frames,
                    "torn": st.torn_frames,
                    "seq_gaps": st.seq_gaps,
                    "coverage": round(st.coverage, 3),
                    "age_ms": round((time.monotonic() - st.last_packet_t) * 1000)
                    if st.last_packet_t
                    else None,
                }
                for st in sorted(self.states.values(), key=lambda s: s.ctrl.column)
            ],
        }

    def summary_line(self) -> str:
        s = self.stats
        cov = " ".join(
            f"c{st.ctrl.column}:{st.complete_frames}" for st in
            sorted(self.states.values(), key=lambda x: x.ctrl.column)
        )
        return (
            f"frames={s.frames} fps={s.fps:5.2f} pkts={s.packets} "
            f"torn={s.torn} bad={s.violations} [{cov}]"
        )


# --------------------------------------------------------------------------
# receiver


class DDPReceiver(threading.Thread):
    """Binds UDP 4048 and pumps packets into a :class:`DDPSink`."""

    def __init__(self, sink: DDPSink, *, host: str = "0.0.0.0", port: Optional[int] = None):
        super().__init__(daemon=True, name="ddp-receiver")
        self.sink = sink
        self.host = host
        self.port = port if port is not None else sink.wall.network.ddp_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:  # so several sinks, and a real controller, can share the port
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(0.5)
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                raw, addr = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            self.sink.feed(raw, src_ip=addr[0])

    def stop(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# renderers


def frame_to_png(frame: np.ndarray, scale: int = 4, grid: bool = False,
                 wall: Optional[Wall] = None) -> bytes:
    from PIL import Image

    img = Image.fromarray(frame, "RGB")
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    if grid and wall is not None and scale >= 2:
        from PIL import ImageDraw

        d = ImageDraw.Draw(img)
        for c in range(1, wall.n_columns):
            x = c * wall.panel_w * scale
            d.line([(x, 0), (x, img.height)], fill=(255, 0, 255), width=1)
        for r in range(1, wall.n_rows):
            y = r * wall.panel_h * scale
            d.line([(0, y), (img.width, y)], fill=(0, 128, 255), width=1)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def frame_to_ansi(frame: np.ndarray, step: int = 2) -> str:
    """Half-block terminal render.  One character cell is two vertical pixels."""
    f = frame[::step, ::step]
    h = f.shape[0] - (f.shape[0] % 2)
    lines = []
    for y in range(0, h, 2):
        row = []
        for x in range(f.shape[1]):
            tr, tg, tb = f[y, x]
            br, bg, bb = f[y + 1, x]
            row.append(f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m▀")
        lines.append("".join(row) + "\x1b[0m")
    return "\n".join(lines)


class PngWriter:
    def __init__(self, out_dir: Path, *, scale: int = 4, every: int = 1,
                 limit: Optional[int] = None, grid: bool = False,
                 wall: Optional[Wall] = None):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.scale, self.every, self.limit = scale, every, limit
        self.grid, self.wall = grid, wall
        self.n = 0
        self.written = 0
        self.done = threading.Event()

    def __call__(self, frame: np.ndarray) -> None:
        i, self.n = self.n, self.n + 1
        if i % self.every:
            return
        if self.limit is not None and self.written >= self.limit:
            self.done.set()
            return
        path = self.dir / f"frame_{i:06d}.png"
        path.write_bytes(frame_to_png(frame, self.scale, self.grid, self.wall))
        self.written += 1
        if self.limit is not None and self.written >= self.limit:
            self.done.set()
