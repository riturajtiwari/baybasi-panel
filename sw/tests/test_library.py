"""The playlist timeline and the manifest that keeps two walls identical."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from baybasi.library import Library, LibraryError, compare_manifests

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _make(path: Path, spec: str, frames: int = 1):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", spec]
    if frames == 1:
        cmd += ["-frames:v", "1"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture
def lib(tmp_path, wall):
    return Library(tmp_path / "data", wall.width, wall.height, wall.render.fps)


@pytest.fixture
def still(tmp_path):
    return _make(tmp_path / "still.png", "testsrc2=size=640x480")


@pytest.fixture
def clip(tmp_path):
    return _make(tmp_path / "clip.mp4",
                 "testsrc2=size=320x240:rate=30:duration=1", frames=0)


def test_still_holds_for_its_duration_in_frames(lib, still):
    lib.add_file(still, fit="letterbox", duration=4.0)
    tl = lib.build_timeline()
    assert tl.total_frames == 120          # 4 s at 30 fps
    assert tl.slots[0].cache.n_frames == 1  # cached once, held by the playlist


def test_video_uses_its_natural_length(lib, clip):
    lib.add_file(clip, fit="crop", duration=0)
    tl = lib.build_timeline()
    assert 28 <= tl.total_frames <= 32


def test_timeline_locate_walks_the_playlist_and_wraps(lib, still, clip):
    lib.add_file(still, duration=2.0)      # 60 frames
    lib.add_file(clip, duration=1.0)       # 30 frames
    tl = lib.build_timeline()
    assert tl.total_frames == 90
    assert tl.locate(0)[0].item.filename == "still.png"
    assert tl.locate(59)[0].item.filename == "still.png"
    assert tl.locate(60)[0].item.filename == "clip.mp4"
    # The wall runs for ever off a wall clock, so wrapping has to be exact.
    assert tl.locate(90)[0].item.filename == "still.png"
    assert tl.locate(9_000_000)[0].item.filename == "still.png"


def test_identical_libraries_produce_identical_digests(tmp_path, wall, still):
    a = Library(tmp_path / "a", wall.width, wall.height, wall.render.fps)
    b = Library(tmp_path / "b", wall.width, wall.height, wall.render.fps)
    a.add_file(still, duration=3.0)
    b.add_file(still, duration=3.0)
    assert a.manifest()["digest"] == b.manifest()["digest"]
    assert compare_manifests(a.manifest(), b.manifest()) == []


def test_order_alone_changes_the_digest(lib, still, clip):
    i1 = lib.add_file(still, duration=1.0)
    i2 = lib.add_file(clip, duration=1.0)
    first = lib.manifest()
    lib.reorder([i2.id, i1.id])
    second = lib.manifest()
    assert first["digest"] != second["digest"]
    diffs = compare_manifests(first, second)
    assert any("order" in d for d in diffs)


def test_compare_names_the_difference_an_operator_can_act_on(lib, still, clip):
    lib.add_file(still, duration=1.0)
    lib.add_file(clip, duration=1.0)
    mine = lib.manifest()
    theirs = json.loads(json.dumps(mine))
    theirs["items"][0]["fit"] = "crop"
    theirs["digest"] = "different"
    diffs = compare_manifests(mine, theirs)
    assert any("fit letterbox vs crop" in d for d in diffs)

    theirs = json.loads(json.dumps(mine))
    theirs["items"].pop()
    theirs["digest"] = "different"
    assert any("only on A" in d for d in compare_manifests(mine, theirs))


def test_disabled_items_leave_the_timeline(lib, still, clip):
    i1 = lib.add_file(still, duration=1.0)
    lib.add_file(clip, duration=1.0)
    before = lib.build_timeline().total_frames
    lib.set_enabled(i1.id, False)
    assert lib.build_timeline().total_frames == before - 30


def test_changing_fit_rebuilds_the_cache_and_the_digest(lib, still):
    item = lib.add_file(still, fit="letterbox", duration=1.0)
    a = lib.manifest()
    lib.set_fit(item.id, "crop")
    b = lib.manifest()
    assert a["digest"] != b["digest"]
    assert b["items"][0]["pixels_sha256"] != a["items"][0]["pixels_sha256"]


def test_the_same_file_twice_is_one_item(lib, still, tmp_path):
    copy = tmp_path / "copy.png"
    copy.write_bytes(still.read_bytes())
    lib.add_file(still)
    lib.add_file(copy)
    assert len(lib.items) == 1     # content-addressed, so a rename is not a dupe


def test_rubbish_is_rejected_at_upload_not_at_playback(lib, tmp_path):
    junk = tmp_path / "notmedia.png"
    junk.write_bytes(b"this is not a png")
    with pytest.raises(LibraryError):
        lib.add_file(junk)
    assert lib.items == {}


def test_unsupported_extension_is_rejected(lib, tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("hello")
    with pytest.raises(LibraryError, match="not supported"):
        lib.add_file(doc)


def test_delete_removes_the_media_and_the_cache(lib, still):
    item = lib.add_file(still)
    assert list(lib.cache_dir.glob("*.raw"))
    lib.remove(item.id)
    assert not list(lib.cache_dir.glob("*.raw"))
    assert not list(lib.media_dir.glob("*.png"))


def test_fit_policies_produce_different_pixels(lib, still):
    item = lib.add_file(still, fit="letterbox")
    lb = lib.cache.open_frames(item.id, "letterbox")[0]
    lib.cache.ensure(lib.media_dir / item.stored_name, item.id, "crop",
                     kind=item.kind)
    cr = lib.cache.open_frames(item.id, "crop")[0]
    assert lb.shape == cr.shape == (192, 64, 3)
    assert not (lb == cr).all()
    # Letterbox pads: the top and bottom rows of a 4:3 source must be black.
    assert lb[0].max() == 0 and lb[-1].max() == 0
