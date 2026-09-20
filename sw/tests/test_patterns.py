"""Properties the bench test patterns have to hold.

``ident`` is the one the eye depends on, so its two promises are asserted here
rather than trusted: a stable hue per output, and neighbouring outputs far
enough apart to tell apart in a photograph taken minutes later.
"""

import colorsys

import numpy as np
import pytest

from baybasi import patterns


def _panel_hue(frame: np.ndarray, output: int, column: int = 0) -> float:
    """Mean hue of one panel, in degrees, ignoring the white marker row."""
    y0, x0 = (output - 1) * 16, column * 16
    tile = frame[y0 + 1 : y0 + 16, x0 : x0 + 16].reshape(-1, 3).astype(float)
    lit = tile[tile.sum(axis=1) > 40]
    h, _s, _v = colorsys.rgb_to_hsv(*(lit.mean(axis=0) / 255.0))
    return h * 360.0


def _sep(a: float, b: float) -> float:
    """Separation of two hues on the wheel, 0..180 degrees."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def test_ident_hue_does_not_move(wall):
    """The reason ident exists.

    ``flow`` scrolls the hue, so a panel is every colour within six seconds -
    longer than it takes to move a JST lead from J1 to J2. An identity that
    changes while you walk round the bench is not an identity.
    """
    p = patterns.build("ident", wall)
    for output in range(1, 13):
        hues = [_panel_hue(p.frame(i), output) for i in (0, 37, 120, 601)]
        assert max(_sep(h, hues[0]) for h in hues) < 1.0, (
            f"output {output} hue drifted across frames: {hues}"
        )


def test_ident_gives_every_output_a_distinct_hue(wall):
    p = patterns.build("ident", wall)
    f = p.frame(0)
    hues = [_panel_hue(f, o) for o in range(1, 13)]
    for a in range(12):
        for b in range(a + 1, 12):
            assert _sep(hues[a], hues[b]) > 20.0, (
                f"outputs {a + 1} and {b + 1} share a hue: "
                f"{hues[a]:.0f} vs {hues[b]:.0f}"
            )


def test_ident_puts_adjacent_outputs_near_opposite(wall):
    """A 1/12 stride would leave J1 and J2 only 30 degrees apart - two shades
    of orange. The 5/12 stride makes the pairs actually compared on the bench
    near-opposites."""
    p = patterns.build("ident", wall)
    f = p.frame(0)
    hues = [_panel_hue(f, o) for o in range(1, 13)]
    for o in range(11):
        assert _sep(hues[o], hues[o + 1]) > 120.0, (
            f"J{o + 1} and J{o + 2} are only "
            f"{_sep(hues[o], hues[o + 1]):.0f} degrees apart"
        )


def test_ident_marks_each_panel_with_its_output_number(wall):
    p = patterns.build("ident", wall)
    f = p.frame(0)
    for output in range(1, 13):
        top = f[(output - 1) * 16, 0:16]
        white = int(np.all(top == 255, axis=-1).sum())
        assert white == output, f"output {output} drew {white} markers"


@pytest.mark.parametrize("name", ["flow", "ident"])
def test_motion_patterns_move_every_pixel(wall, name):
    """Both are throughput tests. A pattern that leaves most of the frame
    untouched proves nothing about the wire or the driver."""
    p = patterns.build(name, wall)
    changed = (p.frame(0) != p.frame(10)).any(axis=-1).sum()
    total = wall.width * wall.height
    assert changed > 0.95 * total, f"{name} changed only {changed} of {total}"


def test_flow_keeps_neighbouring_outputs_apart(wall):
    """flow's hue scrolls, but at any one instant J1/J2/J3 must still be a
    third of the wheel apart - that is what makes it read as one image."""
    p = patterns.build("flow", wall)
    for i in (0, 60, 120):
        f = p.frame(i)
        hues = [_panel_hue(f, o) for o in (1, 2, 3)]
        for a, b in ((0, 1), (1, 2), (0, 2)):
            assert _sep(hues[a], hues[b]) > 60.0, (
                f"frame {i}: J{a + 1} and J{b + 1} only "
                f"{_sep(hues[a], hues[b]):.0f} degrees apart"
            )
