"""The driver loop: pacing, hot reload, and not dying on a bad frame."""

import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from baybasi.driver import Driver, read_status
from baybasi.library import Library
from baybasi.sink import DDPReceiver, DDPSink


@pytest.fixture
def sink(wall):
    s = DDPSink(wall)
    rx = DDPReceiver(s, host="127.0.0.1", port=wall.network.ddp_port)
    rx.start()
    yield s
    rx.stop()
    s.close()


def _drive(wall, tmp_path, **kw):
    wall.network.broadcast = "127.0.0.1"
    d = Driver(wall, status_dir=tmp_path, control=False, **kw)
    return d


def test_pattern_reaches_the_sink_untorn(wall, sink, tmp_path):
    d = _drive(wall, tmp_path, pattern="scroll")
    d.run(max_frames=20, report_every=999)
    time.sleep(0.3)
    assert sink.stats.frames >= 18
    assert sink.stats.torn == 0
    assert sink.stats.violations == 0


def test_driver_holds_the_frame_rate(wall, sink, tmp_path):
    wall.render.fps = 30
    d = _drive(wall, tmp_path, pattern="bars")
    t0 = time.monotonic()
    d.run(max_frames=45, report_every=999)
    elapsed = time.monotonic() - t0
    # 45 frames at 30 fps is 1.5 s. Allow slack for a loaded CI box, but a
    # driver that is not pacing at all finishes in milliseconds.
    assert 1.2 < elapsed < 3.0
    assert d.stages.total < 1000 / wall.render.fps
    # A general-purpose host is not a real-time one, so the odd late tick is
    # honest. What must not happen is systematic slipping.
    assert d.stats.dropped <= 1


def test_shutdown_blacks_the_wall(wall, sink, tmp_path):
    frames = []
    sink.on_frame = frames.append
    d = _drive(wall, tmp_path, pattern="solid")
    d.run(max_frames=5, report_every=999)
    time.sleep(0.3)
    sink.flush()
    assert frames, "nothing arrived"
    assert frames[-1].max() == 0, "the last frame sent should be black"


def test_status_file_is_written_for_the_upload_utility(wall, sink, tmp_path):
    d = _drive(wall, tmp_path, pattern="gray")
    d.run(max_frames=40, report_every=999)
    doc = read_status(tmp_path)
    assert doc is not None
    assert doc["fps_target"] == wall.render.fps
    assert doc["frames"] > 0
    assert "stages" in doc and doc["stages"]["total_ms"] >= 0


def test_a_broken_frame_source_does_not_kill_the_wall(wall, sink, tmp_path):
    d = _drive(wall, tmp_path, pattern="bars")

    calls = {"n": 0}
    real = d.pattern.frame

    def flaky(i):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("a corrupt media file")
        return real(i)

    d.pattern.frame = flaky
    d.run(max_frames=8, report_every=999)
    assert d.stats.errors == 1
    assert d.stats.frames == 8      # it kept going


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_playlist_reloads_without_a_restart(wall, sink, tmp_path):
    src = tmp_path / "a.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=200x200", "-frames:v", "1", str(src)],
                   check=True)
    lib = Library(tmp_path / "data", wall.width, wall.height, wall.render.fps)
    lib.add_file(src, duration=1.0)

    d = _drive(wall, tmp_path, library=lib)
    assert d.timeline.total_frames == 30
    first = d.timeline.digest

    # The upload utility adds an item in another process while we run.
    other = tmp_path / "b.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "smptebars=size=200x200", "-frames:v", "1", str(other)],
                   check=True)
    Library(tmp_path / "data", wall.width, wall.height,
            wall.render.fps).add_file(other, duration=2.0)

    d.run(max_frames=10, report_every=999)
    assert d.timeline.digest != first
    assert d.timeline.total_frames == 90
    assert d.stats.reloads >= 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_media_added_to_an_empty_playlist_reaches_the_wall(wall, sink, tmp_path):
    """The idle pattern is a fallback, not a mode you get stuck in.

    Starting the driver before uploading anything is the normal order of
    operations, so the fallback has to give way the moment media appears -
    otherwise the utility's preview and the wall disagree, silently.
    """
    lib = Library(tmp_path / "data", wall.width, wall.height, wall.render.fps)
    d = _drive(wall, tmp_path, library=lib)
    d.run(max_frames=3, report_every=999)
    assert d.current_slot_title == "(empty playlist)"

    src = tmp_path / "late.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=300x300", "-frames:v", "1", str(src)],
                   check=True)
    Library(tmp_path / "data", wall.width, wall.height,
            wall.render.fps).add_file(src, duration=2.0)

    d.run(max_frames=3, report_every=999)
    assert d.current_slot_title == "late.png"


def test_an_explicit_pattern_still_overrides_the_playlist(wall, sink, tmp_path):
    lib = Library(tmp_path / "data", wall.width, wall.height, wall.render.fps)
    d = _drive(wall, tmp_path, library=lib, pattern="bars")
    d.run(max_frames=3, report_every=999)
    assert d.current_slot_title == "pattern:bars"


def test_empty_playlist_shows_a_diagnostic_not_black(wall, sink, tmp_path):
    lib = Library(tmp_path / "data", wall.width, wall.height, wall.render.fps)
    frames = []
    sink.on_frame = frames.append
    d = _drive(wall, tmp_path, library=lib)
    d.run(max_frames=4, report_every=999)
    time.sleep(0.3)
    sink.flush()
    # A dark wall and a broken driver look identical from the floor, so an
    # empty playlist shows the panel-id pattern instead.
    assert any(f.max() > 0 for f in frames[:-1])
