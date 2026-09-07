"""Geometry is the thing that is wrong on the first build. Pin it down."""

import copy

import numpy as np
import pytest

from baybasi.geometry import ChainSpec, GeometryError, Wall, chain_map
from tests.conftest import WALL_DOC


def test_chain_matches_the_teams_verified_formula():
    # local = x * 16 + (y if x % 2 == 0 else 15 - y)
    expected = np.zeros(256, dtype=np.int32)
    for x in range(16):
        for y in range(16):
            expected[x * 16 + (y if x % 2 == 0 else 15 - y)] = y * 16 + x
    assert np.array_equal(chain_map(16, 16, ChainSpec()), expected)


def test_chain_is_a_permutation(wall):
    for start in ("top_left", "top_right", "bottom_left", "bottom_right"):
        for serp in (True, False):
            m = chain_map(16, 16, ChainSpec(start=start, serpentine=serp))
            assert sorted(m.tolist()) == list(range(256))


def test_every_pixel_is_driven_exactly_once(wall):
    cov = wall.coverage()
    assert cov == {"total": 12288, "driven": 12288, "unmapped": 0, "duplicated": 0}


def test_controller_owns_the_documented_budget(wall):
    for c in wall.controllers:
        assert c.n_pixels == 3072
        assert c.n_bytes == 9216


def test_output_slots_are_contiguous_and_by_output_number(wall):
    # Output N owns bytes [(N-1)*768, N*768). The firmware relies on this.
    c = wall.controller_by_column(0)
    for p in c.panels:
        slot = (p.output - 1) * 256
        block = c.src_index[slot:slot + 256]
        rows = np.unique(block // wall.width // wall.panel_h)
        assert rows.tolist() == [p.row]


def _wall_with(**changes):
    doc = copy.deepcopy(WALL_DOC)
    for path, value in changes.items():
        node = doc
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return doc


@pytest.mark.parametrize("doc,fragment", [
    (_wall_with(**{"controllers": WALL_DOC["controllers"][:3]}), "column"),
    (_wall_with(**{"network.pixels_per_packet": 600}), "1472"),
    (_wall_with(**{"color_order": "XYZ"}), "color_order"),
    (_wall_with(**{"render.brightness": 4.0}), "brightness"),
])
def test_bad_config_fails_at_load_not_at_30_fps(doc, fragment):
    with pytest.raises(GeometryError) as exc:
        Wall.from_dict(doc)
    assert fragment in str(exc.value)


def test_duplicate_output_is_rejected():
    doc = copy.deepcopy(WALL_DOC)
    doc["controllers"][0]["panels"][1]["output"] = 1
    with pytest.raises(GeometryError, match="used twice"):
        Wall.from_dict(doc)


def test_panel_transform_moves_pixels_without_losing_any():
    doc = copy.deepcopy(WALL_DOC)
    doc["controllers"][0]["panels"][0]["transform"] = "rot180"
    w = Wall.from_dict(doc)
    assert w.coverage()["driven"] == 12288
    plain = Wall.from_dict(WALL_DOC).controller_by_column(0).src_index
    turned = w.controller_by_column(0).src_index
    assert not np.array_equal(plain[:256], turned[:256])
    assert sorted(plain[:256].tolist()) == sorted(turned[:256].tolist())
