"""The driver: playlist or pattern in, DDP packets out, 30 fps, on the clock.

Structure of one tick:

    wait for the next wall-clock frame boundary   (WallClockPacer)
    look the global frame index up in the timeline (Library)
    read that frame from the memory-mapped cache
    gamma -> brightness -> dither                  (Pipeline)
    gather into four controller buffers, packetise, send, broadcast PUSH

The frame index comes from wall-clock time, not from a counter, so the two
displays stay together with no messages between them, and so a Pi that falls
behind rejoins the correct frame instead of playing a delayed copy for ever.

The driver measures each stage separately.  When it cannot keep up, the log
says which stage was slow, because "dropped frames" on its own tells you
nothing you can act on.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import numpy as np

from .control import ControlPlane
from .geometry import Wall
from .library import Library, Timeline, _atomic_write
from .patterns import Pattern, build as build_pattern
from .pixels import Pipeline
from .sender import DDPSender, WallClockPacer

log = logging.getLogger("baybasi.driver")

STATUS_FILE = "driver-status.json"
IDLE_PATTERN = "id"


@dataclass
class StageTimes:
    """Rolling per-stage cost, in milliseconds."""

    fetch: float = 0.0
    render: float = 0.0
    pack: float = 0.0
    send: float = 0.0
    total: float = 0.0
    _alpha: float = 0.1

    def update(self, fetch: float, render: float, pack: float, send: float) -> None:
        a = self._alpha
        self.fetch += a * (fetch * 1000 - self.fetch)
        self.render += a * (render * 1000 - self.render)
        self.pack += a * (pack * 1000 - self.pack)
        self.send += a * (send * 1000 - self.send)
        self.total = self.fetch + self.render + self.pack + self.send

    def slowest(self) -> str:
        return max(
            (("decode", self.fetch), ("gamma/dither", self.render),
             ("pack", self.pack), ("send", self.send)),
            key=lambda kv: kv[1],
        )[0]

    def as_dict(self) -> Dict[str, float]:
        return {
            "fetch_ms": round(self.fetch, 3),
            "render_ms": round(self.render, 3),
            "pack_ms": round(self.pack, 3),
            "send_ms": round(self.send, 3),
            "total_ms": round(self.total, 3),
        }


@dataclass
class DriverStats:
    started: float = field(default_factory=time.time)
    frames: int = 0
    dropped: int = 0            # frame indices the clock skipped over
    late: int = 0               # ticks whose deadline had already passed
    overruns: int = 0           # ticks whose work exceeded the frame period
    reloads: int = 0
    errors: int = 0
    last_error: str = ""


class Driver:
    def __init__(
        self,
        wall: Wall,
        *,
        library: Optional[Library] = None,
        pattern: Optional[str] = None,
        pattern_kwargs: Optional[dict] = None,
        status_dir: Optional[Path] = None,
        control: bool = True,
        sender: Optional[DDPSender] = None,
    ):
        self.wall = wall
        self.library = library
        self.pipeline = Pipeline(wall)
        self.sender = sender or DDPSender(wall, pipeline=self.pipeline)
        self.pacer = WallClockPacer(wall.render.fps, wall.render.epoch)
        self.stats = DriverStats()
        self.stages = StageTimes()
        self.status_dir = Path(status_dir) if status_dir else None

        # A pattern asked for on the command line overrides the playlist for
        # the life of the process.  The idle pattern below is a different
        # thing: a fallback for an empty playlist, which must give way the
        # moment media appears.
        self.pattern: Optional[Pattern] = (
            build_pattern(pattern, wall, **(pattern_kwargs or {})) if pattern else None
        )
        self.pattern_name = pattern
        self._idle: Optional[Pattern] = None

        self.timeline: Optional[Timeline] = None
        self._sequences: Dict[tuple, object] = {}
        self._lib_mtime = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.current_slot_title = ""

        self.control = ControlPlane(wall) if control else None
        self._last_status_write = 0.0
        self._reload_pending = threading.Event()

        if self.library is not None:
            self.reload()

    # ---- playlist ------------------------------------------------------

    def reload(self) -> None:
        """Re-read the library and recompile the timeline, without a restart."""
        if self.library is None:
            return
        with self._lock:
            self.library.load()
            self.timeline = self.library.build_timeline()
            self._sequences.clear()
            self._lib_mtime = self.library.mtime()
            self.stats.reloads += 1
        log.info(
            "playlist: %d item(s), %d frames, %.1fs, digest %s",
            len(self.timeline.slots), self.timeline.total_frames,
            self.timeline.total_frames / max(1, self.wall.render.fps),
            self.timeline.digest[:12],
        )

    def request_reload(self) -> None:
        self._reload_pending.set()

    def _check_reload(self) -> None:
        if self._reload_pending.is_set():
            self._reload_pending.clear()
            self.reload()
            return
        if self.library is not None and self.library.mtime() != self._lib_mtime:
            self.reload()

    def _sequence(self, slot):
        key = (slot.item.id, slot.item.fit)
        seq = self._sequences.get(key)
        if seq is None:
            seq = self.library.cache.open_frames(slot.item.id, slot.item.fit)
            self._sequences[key] = seq
        return seq

    # ---- frame source --------------------------------------------------

    def frame_for(self, index: int) -> np.ndarray:
        if self.pattern is not None:
            self.current_slot_title = f"pattern:{self.pattern_name}"
            return self.pattern.frame(index)

        tl = self.timeline
        if tl is None or not tl.slots:
            # Nothing to play.  Show something diagnostic rather than black:
            # a dark wall and a broken driver look identical from the floor.
            self.current_slot_title = "(empty playlist)"
            if self._idle is None:
                self._idle = build_pattern(IDLE_PATTERN, self.wall)
            return self._idle.frame(index)

        # Media has appeared since the last empty tick: drop the fallback so a
        # reload actually reaches the wall.
        self._idle = None

        found = tl.locate(index)
        if found is None:
            self.current_slot_title = "(no slot)"
            return np.zeros((self.wall.height, self.wall.width, 3), np.uint8)
        slot, local = found
        self.current_slot_title = slot.item.display_title
        return self._sequence(slot)[local]

    # ---- main loop -----------------------------------------------------

    def run(self, *, max_frames: Optional[int] = None,
            report_every: float = 10.0) -> None:
        if self.control:
            self.control.start()
        self._warm_up()
        period = 1.0 / self.wall.render.fps
        next_report = time.monotonic() + report_every
        log.info("driver up: %s", self.wall.describe().splitlines()[0])
        log.info("pacing %d fps against wall clock, epoch %.0f",
                 self.wall.render.fps, self.wall.render.epoch)

        try:
            while not self._stop.is_set():
                index = self.pacer.wait()
                t0 = time.perf_counter()

                self._check_reload()

                try:
                    frame = self.frame_for(index)
                except Exception as exc:            # a bad file must not kill the wall
                    self.stats.errors += 1
                    self.stats.last_error = repr(exc)
                    log.exception("frame %d failed, sending black", index)
                    frame = np.zeros((self.wall.height, self.wall.width, 3), np.uint8)
                t1 = time.perf_counter()

                wire = self.pipeline.to_wire8(frame)
                t2 = time.perf_counter()

                pre = self.sender.build_from_wire(wire)
                t3 = time.perf_counter()

                self.sender.send_prebuilt(pre)
                t4 = time.perf_counter()

                self.stages.update(t1 - t0, t2 - t1, t3 - t2, t4 - t3)
                self.stats.frames += 1
                if (t4 - t0) > period:
                    self.stats.overruns += 1

                self.stats.dropped = self.pacer.stats.skipped
                self.stats.late = self.pacer.stats.late

                now = time.monotonic()
                if now >= next_report:
                    self._report()
                    next_report = now + report_every
                self._write_status()

                if max_frames is not None and self.stats.frames >= max_frames:
                    break
        finally:
            self.shutdown()

    # ---- reporting -----------------------------------------------------

    def _warm_up(self) -> None:
        """Run one frame through everything before the clock starts.

        The first pass allocates NumPy's working buffers and touches every code
        path for the first time, and it costs enough to miss a 33 ms deadline.
        Doing it here means the driver does not drop its first frame on every
        single start - which otherwise looks like a fault and is not one.
        """
        blank = np.zeros((self.wall.height, self.wall.width, 3), np.uint8)
        t0 = time.perf_counter()
        self.sender.build_from_wire(self.pipeline.to_wire8(blank), seq=0)
        log.debug("warm-up frame took %.2f ms", (time.perf_counter() - t0) * 1000)
        # The warm-up is not a real frame; do not let it colour the averages.
        self.sender.stats.pack_s = 0.0

    def _report(self) -> None:
        fps = self.pacer.stats.fps()
        budget = 1000.0 / self.wall.render.fps
        msg = (
            "%.2f fps  frames=%d dropped=%d late=%d overruns=%d  "
            "stages ms: decode=%.2f render=%.2f pack=%.2f send=%.2f (budget %.1f)"
            % (fps, self.stats.frames, self.stats.dropped, self.stats.late,
               self.stats.overruns, self.stages.fetch, self.stages.render,
               self.stages.pack, self.stages.send, budget)
        )
        if self.stages.total > budget * 0.9 or self.stats.overruns:
            log.warning("%s  <- cannot keep up; slowest stage is %s",
                        msg, self.stages.slowest())
        else:
            log.info(msg)

    def status(self) -> dict:
        tl = self.timeline
        return {
            "pid": os.getpid(),
            "uptime_s": round(time.time() - self.stats.started, 1),
            "fps_target": self.wall.render.fps,
            "fps_actual": round(self.pacer.stats.fps(), 2),
            "frames": self.stats.frames,
            "dropped": self.stats.dropped,
            "late": self.stats.late,
            "overruns": self.stats.overruns,
            "errors": self.stats.errors,
            "last_error": self.stats.last_error,
            "reloads": self.stats.reloads,
            "brightness": round(self.pipeline.brightness, 3),
            "gamma": round(self.pipeline.gamma, 3),
            "now_playing": self.current_slot_title,
            "frame_index": self.pacer.index_now(),
            "timeline": {
                "digest": tl.digest if tl else "",
                "items": len(tl.slots) if tl else 0,
                "total_frames": tl.total_frames if tl else 0,
            },
            "stages": self.stages.as_dict(),
            "send": {
                "packets": self.sender.stats.packets,
                "bytes": self.sender.stats.bytes_out,
                "errors": self.sender.stats.errors,
                "last_error": self.sender.stats.last_error,
            },
            "controllers": self.control.snapshot() if self.control else [],
            "wall_digest": self.wall.digest,
        }

    def _write_status(self) -> None:
        if self.status_dir is None:
            return
        now = time.monotonic()
        if now - self._last_status_write < 1.0:
            return
        self._last_status_write = now
        try:
            _atomic_write(
                self.status_dir / STATUS_FILE,
                json.dumps(self.status(), indent=1).encode(),
            )
        except OSError as exc:
            log.debug("status write failed: %s", exc)

    # ---- lifecycle -----------------------------------------------------

    def stop(self, *_a) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        log.info("shutting down: blacking out the wall")
        try:
            for _ in range(3):     # the controllers fade out after 500 ms anyway
                self.sender.blackout()
                time.sleep(0.01)
        except OSError:
            pass
        if self.control:
            self.control.stop()
        self.sender.close()
        self._report()

    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self.stop)


def read_status(status_dir: Path) -> Optional[dict]:
    p = Path(status_dir) / STATUS_FILE
    try:
        doc = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    doc["stale_s"] = round(time.time() - p.stat().st_mtime, 1)
    return doc
