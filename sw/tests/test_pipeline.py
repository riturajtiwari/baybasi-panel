"""Gamma, brightness, dither, and the pack/unpack round trip."""

import numpy as np
import pytest

from baybasi.geometry import Wall
from baybasi.pixels import Pipeline, gamma_lut, unpack


def test_identity_pipeline_is_lossless(wall, frame):
    p = Pipeline(wall, gamma=1.0, brightness=1.0, dither="none")
    assert np.array_equal(p.to_wire8(frame), frame)


def test_pack_unpack_round_trip(wall, frame):
    p = Pipeline(wall, gamma=1.0, brightness=1.0, dither="none")
    wire = p.to_wire8(frame)
    out = np.zeros_like(frame)
    for c in wall.controllers:
        buf = p.pack(wire, c)
        assert len(buf) == 9216
        unpack(buf, c, wall, out)
    assert np.array_equal(out, frame)


def test_pack_respects_colour_order():
    import copy
    from tests.conftest import WALL_DOC
    doc = copy.deepcopy(WALL_DOC)
    doc["color_order"] = "GRB"
    w = Wall.from_dict(doc)
    p = Pipeline(w, gamma=1.0, brightness=1.0, dither="none")
    f = np.zeros((w.height, w.width, 3), np.uint8)
    f[0, 0] = (10, 20, 30)  # R G B
    buf = p.pack(p.to_wire8(f), w.controller_by_column(0))
    assert buf[:3] == bytes((20, 10, 30))  # G R B on the wire


def test_black_stays_black_and_white_scales(wall):
    p = Pipeline(wall, gamma=2.2, brightness=0.5, dither="bayer8")
    black = np.zeros((wall.height, wall.width, 3), np.uint8)
    assert p.to_wire8(black).max() == 0
    white = np.full((wall.height, wall.width, 3), 255, np.uint8)
    out = p.to_wire8(white)
    # brightness 0.5 after gamma: half of full scale, within one dither step
    assert 126 <= out.mean() <= 129


def test_gamma_is_monotonic():
    lut = gamma_lut(2.2, 1.0)
    assert lut[0] == 0 and lut[255] == 65535
    assert np.all(np.diff(lut.astype(int)) >= 0)


def test_dither_is_deterministic_so_a_still_frame_does_not_shimmer(wall, frame):
    p = Pipeline(wall, gamma=2.2, brightness=0.31, dither="bayer8")
    a, b = p.to_wire8(frame), p.to_wire8(frame)
    assert np.array_equal(a, b)


def test_dither_beats_truncation_on_a_dim_ramp(wall):
    """The whole reason for 16-bit gamma: a dim ramp must not band."""
    ramp = np.zeros((wall.height, wall.width, 3), np.uint8)
    ramp[:] = np.linspace(0, 40, wall.height).astype(np.uint8)[:, None, None]
    dithered = Pipeline(wall, brightness=0.25, dither="bayer8").to_wire8(ramp)
    plain = Pipeline(wall, brightness=0.25, dither="none").to_wire8(ramp)
    # Dithering produces more distinct levels down the ramp than truncation.
    assert len(np.unique(dithered[:, :, 0])) > len(np.unique(plain[:, :, 0]))


def test_brightness_is_live_tunable(wall, frame):
    p = Pipeline(wall)
    p.brightness = 1.0
    bright = p.to_wire8(frame).astype(int).sum()
    p.brightness = 0.25
    dim = p.to_wire8(frame).astype(int).sum()
    assert dim < bright / 3


def test_unmapped_outputs_send_black():
    import copy
    from tests.conftest import WALL_DOC
    doc = copy.deepcopy(WALL_DOC)
    # A wall with only 11 rows wired: output 12 has no panel.
    doc["wall"]["height"] = 176
    for c in doc["controllers"]:
        c["panels"] = c["panels"][:11]
    w = Wall.from_dict(doc)
    p = Pipeline(w, brightness=1.0, dither="none")
    f = np.full((w.height, w.width, 3), 255, np.uint8)
    buf = p.pack(p.to_wire8(f), w.controller_by_column(0))
    assert len(buf) == 9216
    assert set(buf[11 * 768:]) == {0}
