"""Test patterns.

Three of these are named in the handoff and earn their place on the bench:

``id``      every panel captioned with its column and row, so a swapped
            output is a caption in the wrong place instead of a guess.
``strand``  one hue per output, one corner marker per column: proves the
            row-to-output map without needing to read anything.
``scroll``  a single white column moving across the wall.  This is the tear
            detector.  If the four controllers latch at different times the
            line breaks at the column seams, and nothing else shows that.

The rest are cheap and useful: ``chase`` walks the LED chain inside every panel
and is the fastest way to catch a wrong serpentine, ``bars`` and ``gray`` check
colour order and gamma, ``solid`` checks the power supply under load.
"""

from __future__ import annotations

import colorsys
from typing import Callable, Dict, List

import numpy as np

from .geometry import Wall

# 3x5 digits, one string per row, '#' is lit.
_FONT: Dict[str, List[str]] = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
    "-": ["   ", "   ", "###", "   ", "   "],
    ".": ["   ", "   ", "   ", "   ", " # "],
    # Uppercase, same 3x5 cell, added 2026-09-19 for the marquee. A/R and B/D
    # and M/N are the pairs that collide in a 3-px cell if drawn carelessly;
    # these are deliberately distinct.
    " ": ["   ", "   ", "   ", "   ", "   "],
    "A": [" # ", "# #", "###", "# #", "# #"],
    "B": ["## ", "# #", "## ", "# #", "## "],
    "C": ["###", "#  ", "#  ", "#  ", "###"],
    "D": ["## ", "# #", "# #", "# #", "## "],
    "E": ["###", "#  ", "###", "#  ", "###"],
    "F": ["###", "#  ", "###", "#  ", "#  "],
    "G": ["###", "#  ", "# #", "# #", "###"],
    "H": ["# #", "# #", "###", "# #", "# #"],
    "I": ["###", " # ", " # ", " # ", "###"],
    "J": ["  #", "  #", "  #", "# #", "###"],
    "K": ["# #", "# #", "## ", "# #", "# #"],
    "L": ["#  ", "#  ", "#  ", "#  ", "###"],
    "M": ["# #", "###", "###", "# #", "# #"],
    "N": ["## ", "# #", "# #", "# #", "# #"],
    "O": ["###", "# #", "# #", "# #", "###"],
    "P": ["## ", "# #", "## ", "#  ", "#  "],
    "Q": ["###", "# #", "# #", "###", "  #"],
    "R": ["## ", "# #", "## ", "# #", "# #"],
    "S": ["###", "#  ", "###", "  #", "###"],
    "T": ["###", " # ", " # ", " # ", " # "],
    "U": ["# #", "# #", "# #", "# #", "###"],
    "V": ["# #", "# #", "# #", "# #", " # "],
    "W": ["# #", "# #", "###", "###", "# #"],
    "X": ["# #", "# #", " # ", "# #", "# #"],
    "Y": ["# #", "# #", " # ", " # ", " # "],
    "Z": ["###", "  #", " # ", "#  ", "###"],
}


def draw_text(frame: np.ndarray, text: str, x: int, y: int,
              color=(255, 255, 255)) -> None:
    """3x5 digits with a 1-px gap.  Clipped, never raises."""
    h, w = frame.shape[:2]
    col = np.array(color, dtype=np.uint8)
    for ch in text:
        glyph = _FONT.get(ch)
        if glyph is None:
            x += 4
            continue
        for dy, row in enumerate(glyph):
            gy = y + dy
            if not 0 <= gy < h:
                continue
            for dx, c in enumerate(row):
                gx = x + dx
                if c == "#" and 0 <= gx < w:
                    frame[gy, gx] = col
        x += 4


def _hue(i: int, n: int, v: float = 1.0) -> tuple:
    r, g, b = colorsys.hsv_to_rgb((i / max(n, 1)) % 1.0, 1.0, v)
    return int(r * 255), int(g * 255), int(b * 255)


class Pattern:
    """A frame source.  ``frame(i)`` is a pure function of the frame index."""

    name = "pattern"
    #: how many frames before it repeats; 0 means "never", drive it off the clock
    period = 0

    def __init__(self, wall: Wall):
        self.wall = wall

    def blank(self) -> np.ndarray:
        return np.zeros((self.wall.height, self.wall.width, 3), dtype=np.uint8)

    def frame(self, i: int) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class PanelId(Pattern):
    """Column and row number in every panel, on a per-panel background tint."""

    name = "id"
    period = 60

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        pw, ph = self.wall.panel_w, self.wall.panel_h
        blink = (i // 30) % 2 == 0
        for c in range(self.wall.n_columns):
            for r in range(self.wall.n_rows):
                x0, y0 = c * pw, r * ph
                tint = _hue(r, self.wall.n_rows, 0.16)
                f[y0 : y0 + ph, x0 : x0 + pw] = tint
                # 1-px border so panel boundaries are unambiguous
                f[y0, x0 : x0 + pw] = (40, 40, 40)
                f[y0 + ph - 1, x0 : x0 + pw] = (40, 40, 40)
                f[y0 : y0 + ph, x0] = (40, 40, 40)
                f[y0 : y0 + ph, x0 + pw - 1] = (40, 40, 40)
                draw_text(f, str(c), x0 + 2, y0 + 2, (255, 255, 0))
                draw_text(f, f"{r:d}", x0 + 2, y0 + 9, (255, 255, 255))
                # a lit corner pixel that blinks proves the panel is live even
                # if the text is unreadable from the floor
                if blink:
                    f[y0 + 1, x0 + pw - 2] = (255, 0, 255)
        return f


class StrandId(Pattern):
    """One hue per output; column marked by a run of white pixels at the top."""

    name = "strand"
    period = 1

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        pw, ph = self.wall.panel_w, self.wall.panel_h
        for ctrl in self.wall.controllers:
            c = ctrl.column
            for p in ctrl.panels:
                x0, y0 = c * pw, p.row * ph
                f[y0 : y0 + ph, x0 : x0 + pw] = _hue(p.output - 1, 12)
                # column identity: c+1 white pixels along the panel's top edge
                f[y0, x0 + 1 : x0 + 2 + c] = (255, 255, 255)
                # output identity in dark digits, readable up close
                draw_text(f, f"{p.output}", x0 + 5, y0 + 6, (0, 0, 0))
        return f


class ScrollLine(Pattern):
    """A single white column sweeping left to right.  The tearing detector."""

    name = "scroll"

    def __init__(self, wall: Wall, *, speed: int = 1, width: int = 1):
        super().__init__(wall)
        self.speed = max(1, int(speed))
        self.width = max(1, int(width))
        self.period = max(1, wall.width // self.speed)

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        x = (i * self.speed) % self.wall.width
        for k in range(self.width):
            f[:, (x + k) % self.wall.width] = (255, 255, 255)
        # A dim row marker every panel height gives the eye a reference for
        # vertical tearing as well.
        f[:: self.wall.panel_h, :] = np.maximum(
            f[:: self.wall.panel_h, :], np.uint8(24)
        )
        return f


class Chase(Pattern):
    """Walks the LED chain inside every panel.  Catches a wrong serpentine."""

    name = "chase"

    def __init__(self, wall: Wall, *, tail: int = 12):
        super().__init__(wall)
        self.tail = tail
        self.period = wall.panel_w * wall.panel_h

    def frame(self, i: int) -> np.ndarray:
        from .geometry import chain_map

        f = self.blank()
        pw, ph = self.wall.panel_w, self.wall.panel_h
        n = pw * ph
        chain = chain_map(pw, ph, self.wall.chain)
        head = i % n
        panel = np.zeros((ph, pw, 3), dtype=np.uint8)
        for t in range(self.tail):
            pos = (head - t) % n
            v = int(255 * (1 - t / self.tail))
            local = int(chain[pos])
            panel[local // pw, local % pw] = (v, v, v)
        panel[chain[0] // pw, chain[0] % pw] = (255, 0, 0)   # LED 0 marker
        for c in range(self.wall.n_columns):
            for r in range(self.wall.n_rows):
                f[r * ph : (r + 1) * ph, c * pw : (c + 1) * pw] = panel
        return f


class Bars(Pattern):
    """Colour bars: proves the GRB order end to end. Wrong order swaps them."""

    name = "bars"
    period = 1
    COLORS = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (0, 255, 255), (255, 0, 255),
        (255, 255, 255), (0, 0, 0),
    ]

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        n = len(self.COLORS)
        band = self.wall.height // n
        for k, col in enumerate(self.COLORS):
            f[k * band : (k + 1) * band] = col
        # label the primaries so a swap reads as text, not as an opinion
        draw_text(f, "1", 2, 2, (0, 0, 0))
        return f


class Flow(Pattern):
    """Full-frame motion in saturated colour: the video-rate bench test.

    Every pixel changes every frame, which is the honest worst case for the
    wire, the framebuffer and the LED driver. A mostly-black or mostly-static
    pattern proves far less.

    The hue wheel completes once every THREE panels, so at any instant J1, J2
    and J3 sit 120 degrees apart - red-ish, green-ish, blue-ish - and you can
    tell at a glance that neighbouring outputs are slices of one image rather
    than twelve independent displays. The whole field scrolls, so each panel
    also cycles through the wheel over about six seconds.

    Saturation is full. An earlier version built each channel as
    sin()*0.5+0.5, which never lets a channel reach zero: the three always sum
    to ~1.5 and everything comes out pastel, then a white band washed out what
    was left. On a camera it read as green-and-white mush. Proper HSV instead.
    """

    name = "flow"
    period = 0          # continuous; driven off the frame clock
    HUE_SPAN_PX = 48    # one full wheel every three 16 px panels

    def frame(self, i: int) -> np.ndarray:
        h, w = self.wall.height, self.wall.width
        y = np.arange(h, dtype=np.float32)[:, None]
        x = np.arange(w, dtype=np.float32)[None, :]

        # Hue scrolls down the wall; a slight x term keeps the motion diagonal
        # so no column is ever a repeat of its neighbour.
        hue = (y / self.HUE_SPAN_PX + x * 0.004 - i / 180.0) % 1.0

        # Brightness wave, so pixels keep changing even where the hue barely
        # moves. Never reaches zero - a dark panel proves nothing.
        val = 0.70 + 0.30 * np.sin(y * 0.35 + x * 0.22 - i * 0.22)

        # Fully saturated HSV -> RGB, vectorised.
        k = hue * 6.0
        seg = np.floor(k).astype(np.int32) % 6
        f6 = k - np.floor(k)
        one, zero = np.ones_like(hue), np.zeros_like(hue)
        conds = [seg == n for n in range(6)]
        r = np.select(conds, [one, 1.0 - f6, zero, zero, f6, one])
        g = np.select(conds, [f6, one, one, 1.0 - f6, zero, zero])
        b = np.select(conds, [zero, zero, f6, one, one, 1.0 - f6])

        f = np.stack((r, g, b), axis=-1) * val[:, :, None]
        return (np.clip(f, 0.0, 1.0) * 255.0).astype(np.uint8)


class Ident(Pattern):
    """Locked hue per output, full-frame motion.  The jumper-swap test.

    ``flow`` scrolls the hue, so a panel runs the whole colour wheel in about
    six seconds.  That is what you want from a video test and exactly what you
    do not want when the test method is "unplug the lead from J1, plug it into
    J2, compare": moving a JST connector takes longer than six seconds, so both
    panels have been every colour by the time you look.  Identity has to be
    stable to be an identity.

    So here the hue is a pure function of the output number and never moves.
    The motion lives in brightness instead, which keeps the honest part of the
    test - every pixel changes every frame, so the wire, the framebuffer and
    the driver all still carry a full-rate stream.

    The hue stride is 5/12 of the wheel, not 1/12.  Twelve steps of 5 still
    visit all twelve hues (5 and 12 are coprime) but put ADJACENT outputs 150
    degrees apart, so the pairs you actually compare on the bench - J1 vs J2,
    J2 vs J3 - are near-opposites rather than neighbouring shades.

    Each panel also carries its output number as that many white pixels along
    the top edge, so a photograph of one panel is self-identifying.
    """

    name = "ident"
    period = 0          # continuous; driven off the frame clock
    HUE_STRIDE = 5, 12  # coprime: all 12 distinct, adjacent ones 150 deg apart

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        pw, ph = self.wall.panel_w, self.wall.panel_h
        stride, n = self.HUE_STRIDE

        # Brightness wave, shared by the whole wall so the panels stay phase
        # locked to each other.  0.25 .. 1.0: strong contrast, never dead.
        yy = np.arange(self.wall.height, dtype=np.float32)[:, None]
        xx = np.arange(self.wall.width, dtype=np.float32)[None, :]
        val = 0.625 + 0.375 * np.sin(yy * 0.30 + xx * 0.30 - i * 0.18)

        for ctrl in self.wall.controllers:
            c = ctrl.column
            for panel in ctrl.panels:
                x0, y0 = c * pw, panel.row * ph
                rgb = np.array(
                    _hue((panel.output - 1) * stride, n), dtype=np.float32
                )
                tile = val[y0 : y0 + ph, x0 : x0 + pw, None] * rgb
                f[y0 : y0 + ph, x0 : x0 + pw] = tile.astype(np.uint8)
                # Output identity: that many white pixels along the top edge.
                # Twelve fits inside a 16 px panel with room to spare.
                f[y0, x0 + 1 : x0 + 1 + panel.output] = (255, 255, 255)
        return f


class Marquee(Pattern):
    """Scrolling word per output, in that output's colour, over sparkles.

    The showpiece. Every row of the wall is one marquee line running the full
    64 px width, so on the finished wall a single word crosses all four
    controller boards - which is the thing worth demonstrating, because it only
    looks right if four independent boards are latching the same frame.

    Colour is locked to the output number on the same 5/12 stride as ``ident``,
    so adjacent outputs land 150 degrees apart rather than 30. Each output also
    starts the word at a different offset, so J1, J2 and J3 differ in BOTH hue
    and the letters on screen - you can tell them apart in a photograph taken
    minutes apart, which a scrolling-hue pattern cannot promise (see the note
    on ``flow`` above).

    The sparkle layer is deterministic: per-pixel phase and rate are drawn once
    from a seeded generator in __init__, never per frame, so ``frame(i)``
    stays a pure function of i. That is the Pattern contract, and it is what
    lets the wire test compare a sent frame against a received one byte for
    byte.
    """

    name = "marquee"
    period = 0                # replaced in __init__ with the real loop length

    GLYPH_H, CELL = 5, 4      # 3 px glyph + 1 px gap
    HUE_STRIDE = 5, 12
    ROW_PHASE_PX = 13         # coprime with a 32 px strip: well spread rows
    # Tuned for ONE 16x16 panel seen on its own, which is the bench reality
    # and a harder case than the full wall: a 5 px word in a 16 px square
    # leaves a lot of empty board, and sparse sparkles read as dead pixels
    # rather than as a starfield. Denser and blunter than they would need to
    # be across 64x192.
    SPARKLE_FRACTION = 0.20   # ~51 of a panel's 256 pixels are stars
    SPARKLE_CYCLES = (2, 3, 4)  # twinkles per loop; integers keep it seamless
    SPARKLE_SHARPNESS = 3     # blunter = more of them lit at any one instant
    SPARKLE_LEVEL = 0.65      # below the word: sparkle is the backing track

    # A slow wash in the output's own hue under everything, so the empty board
    # around the word carries the colour too and the panel never looks like a
    # few lit dots on black.
    WASH_MIN, WASH_AMP = 0.03, 0.11
    WASH_CYCLES = 2           # per loop, so the wash is seamless as well

    # No digital glow around the glyphs. A 1 px halo exactly fills the 1 px
    # gap between two 3 px letters, and these panels already bloom hard enough
    # at close range to wash a white core into a photograph. Drawn crisp, the
    # LEDs supply the halo themselves.

    def __init__(self, wall: Wall, *, text: str = "BAYBASI", speed: int = 1):
        super().__init__(wall)
        self.text = (text or "BAYBASI").upper()
        # 1 px every 3 frames at speed 1 = 10 px/s. A whole glyph cell every
        # 1.2 s: fast enough to look alive, slow enough to read through a
        # 16 px window.
        self.px_per_frame = max(1, int(speed)) / 3.0
        # Trailing space so the word does not butt against its own repeat.
        # "BAYBASI " is 8 cells = 32 px, which tiles the 64 px wall exactly.
        self.strip = self._build_strip(self.text + " ")

        # The text returns to its start after the strip has passed by once.
        # Declaring it means a capture of exactly this many frames loops with
        # no seam, and the driver knows the pattern is finite.
        self.period = int(round(self.strip.shape[1] / self.px_per_frame))

        rng = np.random.default_rng(0xBA4BA51)
        shape = (wall.height, wall.width)
        self._spark = rng.random(shape) < self.SPARKLE_FRACTION
        self._phase = rng.random(shape).astype(np.float32)
        # A WHOLE number of twinkles per loop, so the sparkle layer comes back
        # into phase at the same moment the text does. A free-running rate
        # would put a visible jump at the loop point of any capture.
        # Kept as INTEGERS so the phase can be reduced with exact integer
        # arithmetic below - i * cycles / period in floating point lands a
        # hair off at the loop point and tips the odd pixel by one level.
        self._cycles = rng.choice(np.asarray(self.SPARKLE_CYCLES),
                                  size=shape).astype(np.int32)

    def _build_strip(self, text: str) -> np.ndarray:
        strip = np.zeros((self.GLYPH_H, self.CELL * len(text)), dtype=bool)
        for n, ch in enumerate(text):
            for dy, row in enumerate(_FONT.get(ch, _FONT[" "])):
                for dx, lit in enumerate(row):
                    if lit == "#":
                        strip[dy, n * self.CELL + dx] = True
        return strip

    def frame(self, i: int) -> np.ndarray:
        pw, ph = self.wall.panel_w, self.wall.panel_h
        out = np.zeros((self.wall.height, self.wall.width, 3), dtype=np.float32)

        # Sparkles first, white, whole wall. Raising a clipped sine to a power
        # turns a slow swell into a brief flash.
        turns = np.mod(i * self._cycles, self.period).astype(np.float32)
        tw = np.sin(2.0 * np.pi * (turns / self.period + self._phase))
        np.clip(tw, 0.0, 1.0, out=tw)
        tw **= self.SPARKLE_SHARPNESS
        tw *= self._spark
        out += (tw * self.SPARKLE_LEVEL)[:, :, None]

        stride, n = self.HUE_STRIDE
        sw = self.strip.shape[1]
        ty = (ph - self.GLYPH_H) // 2
        shift = i * self.px_per_frame

        # Diagonal wash, one array for the whole wall so neighbouring panels
        # stay phase locked when there are twelve of them.
        wy = np.arange(self.wall.height, dtype=np.float32)[:, None]
        wx = np.arange(self.wall.width, dtype=np.float32)[None, :]
        wash = self.WASH_MIN + self.WASH_AMP * (0.5 + 0.5 * np.sin(
            wy * 0.40 + wx * 0.40
            - 2.0 * np.pi * (i % self.period) * self.WASH_CYCLES / self.period))

        for ctrl in self.wall.controllers:
            x0 = ctrl.column * pw
            for panel in ctrl.panels:
                y0 = panel.row * ph
                rgb = np.asarray(_hue((panel.output - 1) * stride, n),
                                 dtype=np.float32) / 255.0

                # ABSOLUTE x, not panel-local: that is what makes one word run
                # across four boards instead of four boards each showing their
                # own copy of it.
                ax = np.arange(x0, x0 + pw, dtype=np.float32)
                off = shift + panel.output * self.ROW_PHASE_PX
                xs = np.mod(np.round(ax - off).astype(np.int64), sw)
                mask = self.strip[:, xs]

                band = out[y0 : y0 + ph, x0 : x0 + pw]
                band += wash[y0 : y0 + ph, x0 : x0 + pw, None] * rgb
                line = band[ty : ty + self.GLYPH_H]
                line[mask] = rgb

        np.clip(out, 0.0, 1.0, out=out)
        return (out * 255.0).astype(np.uint8)


class Gray(Pattern):
    """Vertical grey ramp.  Banding here means gamma or dither is wrong."""

    name = "gray"
    period = 1

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        ramp = np.linspace(0, 255, self.wall.height).astype(np.uint8)
        f[:] = ramp[:, None, None]
        return f


class Solid(Pattern):
    """Flat colour.  Full white is the power-supply and voltage-drop test."""

    name = "solid"
    period = 1

    def __init__(self, wall: Wall, *, color=(255, 255, 255)):
        super().__init__(wall)
        self.color = tuple(int(c) for c in color)

    def frame(self, i: int) -> np.ndarray:
        f = self.blank()
        f[:] = self.color
        return f


BUILDERS: Dict[str, Callable[..., Pattern]] = {
    "id": PanelId,
    "strand": StrandId,
    "scroll": ScrollLine,
    "chase": Chase,
    "bars": Bars,
    "flow": Flow,
    "ident": Ident,
    "marquee": Marquee,
    "gray": Gray,
    "solid": Solid,
}

NAMES = tuple(BUILDERS)


def build(name: str, wall: Wall, **kw) -> Pattern:
    try:
        cls = BUILDERS[name]
    except KeyError:
        raise KeyError(f"unknown pattern {name!r}; try one of {', '.join(NAMES)}") from None
    return cls(wall, **kw)
