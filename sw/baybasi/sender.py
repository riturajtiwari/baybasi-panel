"""Slice a frame into DDP packets, send them, then latch every column at once.

Two rules from the handoff drive the whole design:

* no data packet carries PUSH, and exactly one broadcast PUSH ends a frame -
  latching per controller tears visibly at the column seams;
* the payload never exceeds 1472 bytes, because the W5500 does not fragment IP.

Both are asserted here rather than trusted.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from . import ddp
from .geometry import Controller, Wall
from .pixels import Pipeline


@dataclass
class SendStats:
    frames: int = 0
    packets: int = 0
    bytes_out: int = 0
    errors: int = 0
    last_error: str = ""
    pack_s: float = 0.0
    send_s: float = 0.0


@dataclass
class PrebuiltFrame:
    """A frame already turned into wire packets, ready to blast."""

    packets: List[Tuple[str, bytes]]   # (destination ip, datagram)
    push: bytes
    n_bytes: int


class DDPSender:
    def __init__(self, wall: Wall, *, pipeline: Optional[Pipeline] = None,
                 broadcast: Optional[str] = None, port: Optional[int] = None,
                 sequence: bool = True, sock: Optional[socket.socket] = None):
        self.wall = wall
        self.pipeline = pipeline or Pipeline(wall)
        self.broadcast = broadcast or wall.network.broadcast
        self.port = port if port is not None else wall.network.ddp_port
        self.use_sequence = sequence
        self.stats = SendStats()
        self._seq = 0
        self._owns_sock = sock is None
        self.sock = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)

    # ---- addressing ----------------------------------------------------

    def dest_id(self, ctrl: Controller) -> int:
        if self.wall.network.id_mode == "per_controller":
            return ctrl.ddp_id
        return ddp.ID_DEFAULT_OUTPUT

    # ---- building ------------------------------------------------------

    def next_seq(self) -> int:
        if not self.use_sequence:
            return 0
        self._seq = ddp.next_sequence(self._seq)
        return self._seq

    def build_from_wire(self, wire8: np.ndarray, *,
                        seq: Optional[int] = None) -> PrebuiltFrame:
        """Packetise an already gamma-corrected, dithered frame.

        The driver times gamma and packing separately, so it calls this with
        the output of :meth:`Pipeline.to_wire8` rather than a raw frame.
        """
        seq = self.next_seq() if seq is None else seq
        t0 = time.perf_counter()
        ppp = self.wall.network.pixels_per_packet
        out: List[Tuple[str, bytes]] = []
        total = 0
        for ctrl in self.wall.controllers:
            buf = self.pipeline.pack(wire8, ctrl)
            for pkt in ddp.split_frame(
                buf, dest_id=self.dest_id(ctrl), sequence=seq, pixels_per_packet=ppp
            ):
                out.append((ctrl.ip, pkt))
                total += len(pkt)
        push = ddp.build_push_packet(dest_id=ddp.ID_ALL, sequence=seq)
        self.stats.pack_s += time.perf_counter() - t0
        return PrebuiltFrame(packets=out, push=push, n_bytes=total + len(push))

    def build(self, frame: np.ndarray, *, seq: Optional[int] = None) -> PrebuiltFrame:
        return self.build_from_wire(self.pipeline.to_wire8(frame), seq=seq)

    # ---- sending -------------------------------------------------------

    def send_prebuilt(self, pre: PrebuiltFrame) -> None:
        t0 = time.perf_counter()
        port = self.port
        sock = self.sock
        for ip, pkt in pre.packets:
            try:
                sock.sendto(pkt, (ip, port))
            except OSError as exc:
                self.stats.errors += 1
                self.stats.last_error = f"{ip}: {exc}"
        try:
            # One broadcast PUSH.  Every controller latches on the same frame.
            sock.sendto(pre.push, (self.broadcast, port))
        except OSError as exc:
            self.stats.errors += 1
            self.stats.last_error = f"broadcast {self.broadcast}: {exc}"
        self.stats.send_s += time.perf_counter() - t0
        self.stats.frames += 1
        self.stats.packets += len(pre.packets) + 1
        self.stats.bytes_out += pre.n_bytes

    def send_frame(self, frame: np.ndarray) -> None:
        self.send_prebuilt(self.build(frame))

    def blackout(self) -> None:
        """Send one all-black frame.  Used on shutdown so the wall goes dark."""
        self.send_frame(np.zeros((self.wall.height, self.wall.width, 3), np.uint8))

    def close(self) -> None:
        if self._owns_sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def __enter__(self) -> "DDPSender":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


# --------------------------------------------------------------------------
# pacing


@dataclass
class PaceStats:
    ticks: int = 0
    late: int = 0            # a frame whose deadline had already passed
    skipped: int = 0         # frame indices the clock jumped over
    max_lateness_ms: float = 0.0
    recent: List[float] = field(default_factory=list)

    def fps(self) -> float:
        if len(self.recent) < 2:
            return 0.0
        span = self.recent[-1] - self.recent[0]
        return (len(self.recent) - 1) / span if span > 0 else 0.0


class WallClockPacer:
    """Derives the frame index from wall-clock time, and sleeps to the next one.

    Both displays run this against NTP-disciplined ``time.time()`` with the same
    ``EPOCH``, which is the entire synchronisation mechanism: no messages pass
    between them.  The sleep uses the monotonic clock so an NTP slew does not
    turn into a stall, but the *index* always comes from wall time so a step
    correction is absorbed in one frame instead of drifting for ever.
    """

    def __init__(self, fps: float, epoch: float):
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.fps = float(fps)
        self.epoch = float(epoch)
        self.period = 1.0 / self.fps
        self.stats = PaceStats()
        self._last_index: Optional[int] = None

    def index_now(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        return int((now - self.epoch) * self.fps)

    def wait(self) -> int:
        """Block until the next frame boundary; return that frame's index."""
        now = time.time()
        idx = self.index_now(now)
        target_index = idx + 1
        deadline_wall = self.epoch + target_index * self.period

        delta = deadline_wall - now
        if delta > 0:
            # Sleep on the monotonic clock so a wall-clock step cannot hang us.
            end = time.monotonic() + delta
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.25))
        else:
            self.stats.late += 1
            self.stats.max_lateness_ms = max(self.stats.max_lateness_ms, -delta * 1000)

        actual = self.index_now()
        if self._last_index is not None:
            gap = actual - self._last_index
            if gap > 1:
                self.stats.skipped += gap - 1
        self._last_index = actual
        self.stats.ticks += 1
        t = time.monotonic()
        self.stats.recent.append(t)
        if len(self.stats.recent) > 120:
            del self.stats.recent[: len(self.stats.recent) - 120]
        return actual


def check_wire_limits(wall: Wall) -> Sequence[str]:
    """Static checks that would otherwise show up as a dead column on site."""
    problems = []
    ppp = wall.network.pixels_per_packet
    size = ppp * 3 + ddp.HEADER_LEN
    if size > ddp.MAX_UDP_PAYLOAD:
        problems.append(
            f"{ppp} px/packet = {size} B, over the {ddp.MAX_UDP_PAYLOAD} B W5500 limit"
        )
    for c in wall.controllers:
        n_pkts = -(-c.n_bytes // (ppp * 3))
        if c.n_bytes % (ppp * 3):
            pass  # a short final packet is fine
        if n_pkts > 64:
            problems.append(f"column {c.column} needs {n_pkts} packets per frame")
    fps = wall.render.fps
    per_frame = sum(c.n_bytes for c in wall.controllers)
    mbps = per_frame * 8 * fps / 1e6
    if mbps > 80:
        problems.append(f"{mbps:.1f} Mbps of pixel data will not fit on 100 Mbit")
    return problems


def bandwidth_report(wall: Wall) -> str:
    ppp = wall.network.pixels_per_packet
    per_frame_bytes = 0
    per_frame_pkts = 0
    for c in wall.controllers:
        n = -(-c.n_bytes // (ppp * 3))
        per_frame_pkts += n
        per_frame_bytes += c.n_bytes + n * ddp.HEADER_LEN
    per_frame_pkts += 1  # broadcast push
    per_frame_bytes += ddp.HEADER_LEN
    fps = wall.render.fps
    return (
        f"{per_frame_pkts} packets/frame, {per_frame_bytes} B/frame, "
        f"{per_frame_pkts * fps} pps, "
        f"{per_frame_bytes * 8 * fps / 1e6:.2f} Mbps at {fps} fps"
    )
