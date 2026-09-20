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


# ---- marquee --------------------------------------------------------------


def test_marquee_is_a_pure_function_of_the_frame_index(wall):
    """The sparkle layer must be seeded once in __init__, never drawn per
    frame. Two calls for the same i have to be identical, or the wire test's
    byte-for-byte comparison is meaningless and playback desynchronises the
    two displays."""
    p = patterns.build("marquee", wall)
    assert np.array_equal(p.frame(17), p.frame(17))
    q = patterns.build("marquee", wall)
    assert np.array_equal(p.frame(17), q.frame(17)), "two instances disagree"


def test_marquee_scrolls_left_to_right(wall):
    p = patterns.build("marquee", wall)
    row = 7  # inside J1's glyph band
    a = p.frame(0)[row, :, :].max(axis=-1) > 200
    for shift in range(1, 8):
        b = p.frame(shift * 3)[row, :, :].max(axis=-1) > 200
        if np.array_equal(b[shift:], a[:-shift]):
            return
    raise AssertionError("marquee did not move right by its scroll rate")


def test_marquee_gives_adjacent_outputs_different_hues(wall):
    p = patterns.build("marquee", wall)
    f = p.frame(0)
    hues = [_panel_hue(f, o) for o in range(1, 13)]
    for o in range(11):
        assert _sep(hues[o], hues[o + 1]) > 120.0, (
            f"J{o + 1} and J{o + 2} only {_sep(hues[o], hues[o + 1]):.0f} apart"
        )


def test_marquee_offsets_each_row_so_the_letters_differ(wall):
    """Hue alone is not enough: two panels the same colour showing the same
    letters at the same moment would still be hard to tell apart in a photo."""
    p = patterns.build("marquee", wall)
    f = p.frame(0)
    bands = [f[(o - 1) * 16 : o * 16, 0:16].max(axis=-1) > 200 for o in (1, 2, 3)]
    for a, b in ((0, 1), (1, 2), (0, 2)):
        assert not np.array_equal(bands[a], bands[b]), (
            f"J{a + 1} and J{b + 1} show identical glyphs"
        )


def test_marquee_renders_the_requested_word(wall):
    p = patterns.build("marquee", wall, text="hi")
    assert p.strip.shape == (5, 12), "2 letters + trailing space, 4 px per cell"
    # 'H' is the first glyph: outer columns full, middle column only the waist.
    assert p.strip[:, 0].tolist() == [True] * 5
    assert p.strip[:, 1].tolist() == [False, False, True, False, False]


def test_marquee_never_leaves_a_panel_black(wall):
    """A dark panel in a demo reads as a dead board."""
    p = patterns.build("marquee", wall)
    for i in (0, 25, 90):
        f = p.frame(i)
        for o in range(1, 13):
            band = f[(o - 1) * 16 : o * 16, 0:16]
            assert band.max() > 0, f"frame {i}, output {o} is fully black"


def test_marquee_loops_seamlessly(wall):
    """`period` is a promise: a capture of exactly that many frames has to
    join back to its own start with no seam, sparkles included. The sparkle
    phase is reduced with integer arithmetic for exactly this reason - the
    float version left one pixel one level out at the join."""
    p = patterns.build("marquee", wall)
    assert p.period == 96, "BAYBASI at speed 1 is a 3.2 s loop at 30 fps"
    for i in (0, 7, 41):
        assert np.array_equal(p.frame(i), p.frame(i + p.period)), (
            f"frame {i} differs from frame {i + p.period}"
        )


# ---- badge: the one pattern that must not cross a panel boundary ----------


def _badge_cell(p, f, output):
    """The glyph's rectangle inside one panel of column 0."""
    g = p.glyphs[0]
    gh, gw = g.shape
    gy, gx = (16 - gh) // 2, (16 - gw) // 2
    y0 = (output - 1) * 16
    return f[y0 + gy : y0 + gy + gh, gx : gx + gw], (gy, gx, gh, gw)


def test_badge_glyph_cannot_be_clipped_by_the_panel_edge(wall):
    """The whole reason this pattern exists. Every other pattern treats a
    panel as a window onto a bigger image, so a single panel on the bench
    shows half a letter at each edge. Here the glyph has a margin on all four
    sides, so nothing can run off."""
    p = patterns.build("badge", wall)
    for g in p.glyphs:
        gh, gw = g.shape
        gy, gx = (16 - gh) // 2, (16 - gw) // 2
        assert gy >= 1 and gx >= 1, "glyph touches the panel edge"
        assert gy + gh <= 15 and gx + gw <= 15, "glyph runs past the edge"


def test_badge_draws_the_whole_letter_in_the_panel_hue(wall):
    import colorsys
    p = patterns.build("badge", wall)
    i = p.hold // 2                       # mid-hold: alpha is 1
    f = p.frame(i)
    slot = i // p.hold
    for output in (1, 2, 3):
        cell, _ = _badge_cell(p, f, output)
        want = p.glyphs[(slot + output - 1) % len(p.glyphs)]
        lit_hue = colorsys.rgb_to_hsv(*(cell[want].mean(axis=0) / 255.0))[0] * 360
        assert _sep(lit_hue, _panel_hue(f, output)) < 25.0
        # every pixel of the glyph is actually lit
        assert (cell[want].max(axis=-1) > 120).all(), f"J{output} letter has holes"


def test_badge_shows_a_different_letter_on_each_output(wall):
    p = patterns.build("badge", wall)
    f = p.frame(p.hold // 2)
    seen = []
    for output in (1, 2, 3):
        cell, _ = _badge_cell(p, f, output)
        seen.append((cell.max(axis=-1) > 120).tobytes())
    assert len(set(seen)) == 3, "two outputs are showing the same letter"


def test_badge_walks_the_whole_word(wall):
    """J1 must show B, A, Y, B, A, S, I in order.

    The glyph has to be separated from the sparkles first: a sparkle is white,
    a glyph pixel is J1's hue, which is pure red. Hashing the raw lit mask
    instead counts the same letter twice as two different letters, because
    the stars behind it moved.
    """
    p = patterns.build("badge", wall)
    shapes = []
    for slot in range(len(p.text)):
        f = p.frame(slot * p.hold + p.hold // 2)
        cell, _ = _badge_cell(p, f, 1)
        red_only = ((cell[:, :, 0] > 120)
                    & (cell[:, :, 1] < 60) & (cell[:, :, 2] < 60))
        assert np.array_equal(red_only, p.glyphs[slot]), (
            f"slot {slot} is not {p.text[slot]!r}"
        )
        shapes.append(red_only.tobytes())
    assert len(set(shapes)) == len(set(p.text)), "distinct glyph count is wrong"


def test_badge_loops_and_is_pure(wall):
    p = patterns.build("badge", wall)
    assert p.period == p.hold * len(p.text)
    for i in (0, 13, 77):
        assert np.array_equal(p.frame(i), p.frame(i + p.period))
        assert np.array_equal(p.frame(i), p.frame(i))


def test_badge_hues_are_far_apart_on_adjacent_outputs(wall):
    p = patterns.build("badge", wall)
    f = p.frame(p.hold // 2)
    hues = [_panel_hue(f, o) for o in range(1, 13)]
    for o in range(11):
        assert _sep(hues[o], hues[o + 1]) > 120.0
