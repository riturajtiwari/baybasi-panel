"""The upload utility: the flows a non-technical person actually performs."""

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from baybasi.library import Library
from baybasi.webapp import create_app

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


@pytest.fixture
def png_bytes(tmp_path):
    out = tmp_path / "src.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=1600x900", "-frames:v", "1", str(out)],
                   check=True)
    return out.read_bytes()


@pytest.fixture
def client(tmp_path, wall):
    lib = Library(tmp_path / "data", wall.width, wall.height, wall.render.fps)
    app = create_app(wall, lib, status_dir=tmp_path / "data")
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.library = lib
        yield c


def _upload(client, data: bytes, name="photo.png", fit="letterbox"):
    return client.post("/api/upload", content_type="multipart/form-data",
                       data={"file": (io.BytesIO(data), name), "fit": fit})


def test_upload_then_playlist(client, png_bytes):
    r = _upload(client, png_bytes)
    assert r.status_code == 200
    assert r.json["errors"] == []
    state = client.get("/api/state").json
    assert len(state["items"]) == 1
    assert state["items"][0]["fit"] == "letterbox"
    assert state["items"][0]["frames"] == 240      # 8 s default at 30 fps


def test_upload_rejects_rubbish_with_a_readable_reason(client):
    r = _upload(client, b"not an image at all", name="broken.png")
    assert r.status_code == 400
    assert r.json["added"] == []
    assert "broken.png" in r.json["errors"][0]


def test_upload_rejects_an_unsupported_type(client):
    r = _upload(client, b"hello", name="notes.txt")
    assert r.status_code == 400
    assert "not supported" in r.json["errors"][0]


def test_preview_is_the_wall_resolution(client, png_bytes):
    _upload(client, png_bytes)
    item = client.get("/api/state").json["items"][0]
    r = client.get(f"/preview/{item['id']}.png?scale=1")
    assert r.status_code == 200
    from PIL import Image
    img = Image.open(io.BytesIO(r.data))
    assert img.size == (64, 192)


def test_preview_shows_the_crop_the_wall_will_show(client, png_bytes):
    """A landscape photo on a 64x192 wall: the operator has to see this."""
    from PIL import Image
    _upload(client, png_bytes, fit="letterbox")
    item = client.get("/api/state").json["items"][0]
    lb = Image.open(io.BytesIO(
        client.get(f"/preview/{item['id']}.png?scale=1").data))
    assert lb.getpixel((32, 2)) == (0, 0, 0)     # letterboxed: black at the top

    r = client.post(f"/api/item/{item['id']}/fit", json={"fit": "crop"})
    assert r.status_code == 200
    cr = Image.open(io.BytesIO(
        client.get(f"/preview/{item['id']}.png?scale=1").data))
    assert cr.getpixel((32, 2)) != (0, 0, 0)     # cropped: image fills the top


def test_reorder_changes_the_manifest(client, png_bytes, tmp_path):
    _upload(client, png_bytes, name="a.png")
    other = tmp_path / "b.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", "smptebars=size=320x240", "-frames:v", "1", str(other)],
                   check=True)
    _upload(client, other.read_bytes(), name="b.png")

    before = client.get("/api/manifest").json
    ids = [i["id"] for i in client.get("/api/state").json["items"]]
    assert client.post("/api/reorder", json={"order": ids[::-1]}).status_code == 200
    after = client.get("/api/manifest").json
    assert before["digest"] != after["digest"]


def test_compare_endpoint_matches_and_differs(client, png_bytes):
    _upload(client, png_bytes)
    mine = client.get("/api/manifest").json
    assert client.post("/api/compare", json=mine).json["match"] is True

    theirs = json.loads(json.dumps(mine))
    theirs["items"][0]["frames"] = 999
    theirs["digest"] = "x"
    r = client.post("/api/compare", json=theirs).json
    assert r["match"] is False
    assert any("frames" in d for d in r["differences"])


def test_compare_rejects_something_that_is_not_a_manifest(client):
    assert client.post("/api/compare", json={"hello": 1}).status_code == 400


def test_delete(client, png_bytes):
    _upload(client, png_bytes)
    item = client.get("/api/state").json["items"][0]
    assert client.delete(f"/api/item/{item['id']}").status_code == 200
    assert client.get("/api/state").json["items"] == []


def test_reload_touches_the_state_file_the_driver_watches(client, png_bytes):
    _upload(client, png_bytes)
    before = client.library.mtime()
    import time
    time.sleep(0.01)
    assert client.post("/api/reload").status_code == 200
    assert client.library.mtime() >= before


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Baybasi wall" in r.data


def test_now_png_renders_even_with_an_empty_playlist(client):
    from PIL import Image
    r = client.get("/now.png?scale=1")
    assert r.status_code == 200
    assert Image.open(io.BytesIO(r.data)).size == (64, 192)
