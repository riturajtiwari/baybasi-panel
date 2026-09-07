"""Gamma, brightness, dither, and packing frames into controller buffers.

Order matters and is fixed by the handoff: gamma then brightness, both in
16 bit, then dither down to 8 bit.  Dithering last is the point - a large dim
wall shows 8-bit banding badly, and the whole reason to carry 16 bits through
the multiply is so the dither has something to spread.

The dither is an ordered 8x8 Bayer matrix, not error diffusion.  Ordered
dithering is a pure function of position, so a still frame is bit-identical
frame to frame: no shimmer, and the two displays cannot diverge.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from .geometry import Controller, Wall

# The classic 8x8 Bayer threshold matrix, values 0..63.
BAYER8 = np.array(
    [
        [0, 32, 8, 40, 2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44, 4, 36, 14, 46, 6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [3, 35, 11, 43, 1, 33, 9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47, 7, 39, 13, 45, 5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ],
    dtype=np.uint32,
)


def gamma_lut(gamma: float, brightness: float) -> np.ndarray:
    """8-bit sRGB in, 16-bit linear-ish out, with brightness already folded in.

    Folding brightness into the table costs one multiply at build time instead
    of 36 864 multiplies per frame.
    """
    if gamma <= 0:
        raise ValueError(f"gamma must be positive, got {gamma}")
    brightness = float(np.clip(brightness, 0.0, 1.0))
    x = np.arange(256, dtype=np.float64) / 255.0
    y = np.power(x, gamma) * brightness
    return np.rint(y * 65535.0).astype(np.uint16)


class Pipeline:
    """Turns an 8-bit RGB frame into per-controller wire buffers.

    One instance owns the LUT and the tiled dither plane, so the per-frame work
    is two table lookups and a gather.
    """

    def __init__(self, wall: Wall, *, gamma: Optional[float] = None,
                 brightness: Optional[float] = None, dither: Optional[str] = None):
        self.wall = wall
        self._gamma = wall.render.gamma if gamma is None else float(gamma)
        self._brightness = wall.render.brightness if brightness is None else float(brightness)
        self._dither = (wall.render.dither if dither is None else dither).lower()
        self._perm = np.array(wall.color_permutation, dtype=np.intp)
        self._rebuild()

    # ---- live-tunable knobs -------------------------------------------

    @property
    def brightness(self) -> float:
        return self._brightness

    @brightness.setter
    def brightness(self, value: float) -> None:
        self._brightness = float(np.clip(value, 0.0, 1.0))
        self._rebuild()

    @property
    def gamma(self) -> float:
        return self._gamma

    @gamma.setter
    def gamma(self, value: float) -> None:
        self._gamma = float(value)
        self._rebuild()

    def _rebuild(self) -> None:
        self._lut = gamma_lut(self._gamma, self._brightness)
        h, w = self.wall.height, self.wall.width
        if self._dither == "bayer8":
            tile = np.tile(BAYER8, (h // 8 + 1, w // 8 + 1))[:h, :w]
            # Bayer 0..63 -> a threshold inside one 8-bit step of the 16-bit range.
            # One 8-bit step is 65535/255 = 257 counts; spread the 64 levels over it.
            self._dither_plane = (tile * 257 // 64).astype(np.uint32)[:, :, None]
        else:
            self._dither_plane = np.zeros((h, w, 1), dtype=np.uint32)

    # ---- the pipeline --------------------------------------------------

    def to_wire8(self, frame: np.ndarray) -> np.ndarray:
        """``(h, w, 3) uint8`` sRGB -> ``(h, w, 3) uint8`` post-gamma, dithered."""
        if frame.dtype != np.uint8:
            raise TypeError(f"frame must be uint8, got {frame.dtype}")
        if frame.shape != (self.wall.height, self.wall.width, 3):
            raise ValueError(
                f"frame is {frame.shape}, wall wants "
                f"({self.wall.height}, {self.wall.width}, 3)"
            )
        v16 = self._lut[frame].astype(np.uint32)          # gamma + brightness, 16 bit
        # Round to 8 bit with a per-position threshold instead of a constant 0.5.
        out = (v16 + self._dither_plane) // 257
        return np.minimum(out, 255).astype(np.uint8)

    def pack(self, wire8: np.ndarray, ctrl: Controller) -> bytes:
        """Gather one controller's 9216 bytes in output order, in LED colour order."""
        flat = wire8.reshape(-1, 3)
        idx = ctrl.src_index
        buf = np.zeros((idx.size, 3), dtype=np.uint8)
        live = idx >= 0
        buf[live] = flat[idx[live]]
        return buf[:, self._perm].tobytes()

    def pack_all(self, frame: np.ndarray) -> "list[tuple[Controller, bytes]]":
        wire8 = self.to_wire8(frame)
        return [(c, self.pack(wire8, c)) for c in self.wall.controllers]


def unpack(buf: bytes, ctrl: Controller, wall: Wall,
           into: Optional[np.ndarray] = None) -> np.ndarray:
    """Inverse of :meth:`Pipeline.pack`, for the software sink.

    Scatters a controller's wire buffer back onto a ``(h, w, 3)`` frame, so a
    mapping bug shows up as a visibly wrong picture instead of a wrong number.
    """
    if into is None:
        into = np.zeros((wall.height, wall.width, 3), dtype=np.uint8)
    n = ctrl.src_index.size
    arr = np.frombuffer(buf[: n * 3], dtype=np.uint8)
    if arr.size < n * 3:
        arr = np.concatenate([arr, np.zeros(n * 3 - arr.size, dtype=np.uint8)])
    pix = arr.reshape(n, 3)
    # Undo the colour permutation: perm maps wire slot -> rgb channel.
    perm = np.array(wall.color_permutation, dtype=np.intp)
    inv = np.empty(3, dtype=np.intp)
    inv[perm] = np.arange(3, dtype=np.intp)
    rgb = pix[:, inv]
    live = ctrl.src_index >= 0
    into.reshape(-1, 3)[ctrl.src_index[live]] = rgb[live]
    return into


def color_order_bytes(order: str) -> Sequence[int]:
    from .geometry import COLOR_ORDERS
    return COLOR_ORDERS[order.upper()]
