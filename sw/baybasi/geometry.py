"""Wall geometry: YAML in, index arrays out.

The Pi holds all the geometry.  A controller is told only how many bytes it
owns and which of its twelve outputs each run of bytes belongs to, so every
mapping decision - panel chain, row-to-output, a panel mounted upside down -
lives in ``config/wall.yaml`` and is fixed by editing data.

The product of this module is, per controller, one ``int32`` array of length
``outputs * 256`` mapping *wire position* to *source pixel index* in a
row-major ``height x width`` frame.  Packing a frame is then a single NumPy
take, which is what keeps a Pi 3 at 30 fps.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import yaml

OUTPUTS_PER_CONTROLLER = 12

COLOR_ORDERS = {
    "RGB": (0, 1, 2),
    "RBG": (0, 2, 1),
    "GRB": (1, 0, 2),
    "GBR": (1, 2, 0),
    "BRG": (2, 0, 1),
    "BGR": (2, 1, 0),
}

TRANSFORMS = ("none", "rot90", "rot180", "rot270", "flipx", "flipy")


class GeometryError(ValueError):
    """The wall description is inconsistent.  Fail at load, never at 30 fps."""


# --------------------------------------------------------------------------
# panel chain


@dataclass(frozen=True)
class ChainSpec:
    axis: str = "column"       # column | row
    start: str = "top_left"    # top_left | top_right | bottom_left | bottom_right
    serpentine: bool = True

    @staticmethod
    def from_dict(d: Optional[dict]) -> "ChainSpec":
        d = d or {}
        spec = ChainSpec(
            axis=str(d.get("axis", "column")).lower(),
            start=str(d.get("start", "top_left")).lower(),
            serpentine=bool(d.get("serpentine", True)),
        )
        if spec.axis not in ("column", "row"):
            raise GeometryError(f"panel.chain.axis must be column or row, got {spec.axis!r}")
        if spec.start not in ("top_left", "top_right", "bottom_left", "bottom_right"):
            raise GeometryError(f"panel.chain.start is not a corner: {spec.start!r}")
        return spec


def chain_map(w: int, h: int, spec: ChainSpec) -> np.ndarray:
    """``out[i] = y * w + x`` for chain position ``i`` within one panel.

    ``axis: column`` means the strand runs along y: it fills one x at a time.
    ``start`` picks the corner holding LED 0, which sets the direction of the
    first run and, with ``serpentine``, of every run after it.
    """
    major_is_x = spec.axis == "column"
    n_major, n_minor = (w, h) if major_is_x else (h, w)

    major = np.repeat(np.arange(n_major, dtype=np.int32), n_minor)
    minor = np.tile(np.arange(n_minor, dtype=np.int32), n_major)

    if spec.serpentine:
        odd = (major & 1).astype(bool)
        minor = np.where(odd, n_minor - 1 - minor, minor)

    x = major if major_is_x else minor
    y = minor if major_is_x else major

    # `start` mirrors the whole panel.  top_left is the identity.
    if spec.start in ("top_right", "bottom_right"):
        x = w - 1 - x
    if spec.start in ("bottom_left", "bottom_right"):
        y = h - 1 - y

    return (y.astype(np.int32) * w + x.astype(np.int32)).astype(np.int32)


def apply_transform(xy: np.ndarray, w: int, h: int, transform: str) -> np.ndarray:
    """Remap panel-local ``y*w + x`` indices for a panel that is not upright."""
    transform = (transform or "none").lower()
    if transform not in TRANSFORMS:
        raise GeometryError(f"transform must be one of {TRANSFORMS}, got {transform!r}")
    if transform == "none":
        return xy
    if transform in ("rot90", "rot270") and w != h:
        raise GeometryError(f"{transform} needs a square panel, got {w}x{h}")
    x = xy % w
    y = xy // w
    if transform == "flipx":
        x = w - 1 - x
    elif transform == "flipy":
        y = h - 1 - y
    elif transform == "rot180":
        x, y = w - 1 - x, h - 1 - y
    elif transform == "rot90":       # clockwise
        x, y = h - 1 - y, x
    elif transform == "rot270":      # counter-clockwise
        x, y = y, w - 1 - x
    return (y * w + x).astype(np.int32)


# --------------------------------------------------------------------------
# wall


@dataclass(frozen=True)
class PanelPlacement:
    row: int
    output: int                 # physical D1..D12
    transform: str = "none"


@dataclass
class Controller:
    column: int
    ip: str
    ddp_id: int
    panels: List[PanelPlacement]
    src_index: np.ndarray = field(repr=False, default=None)  # wire slot -> frame index

    @property
    def n_pixels(self) -> int:
        return int(self.src_index.size)

    @property
    def n_bytes(self) -> int:
        return self.n_pixels * 3


@dataclass
class RenderSpec:
    fps: int = 30
    gamma: float = 2.2
    brightness: float = 0.5
    dither: str = "bayer8"
    epoch: float = 1767225600.0


@dataclass
class NetworkSpec:
    broadcast: str = "192.168.50.255"
    ddp_port: int = 4048
    control_port: int = 4049
    pixels_per_packet: int = 480
    id_mode: str = "per_controller"


@dataclass
class Wall:
    width: int
    height: int
    panel_w: int
    panel_h: int
    chain: ChainSpec
    color_order: str
    render: RenderSpec
    network: NetworkSpec
    controllers: List[Controller]
    source_path: Optional[Path] = None
    digest: str = ""

    # ---- derived -------------------------------------------------------

    @property
    def n_columns(self) -> int:
        return self.width // self.panel_w

    @property
    def n_rows(self) -> int:
        return self.height // self.panel_h

    @property
    def panel_pixels(self) -> int:
        return self.panel_w * self.panel_h

    @property
    def color_permutation(self) -> Sequence[int]:
        return COLOR_ORDERS[self.color_order]

    def controller_by_column(self, column: int) -> Controller:
        for c in self.controllers:
            if c.column == column:
                return c
        raise KeyError(f"no controller for column {column}")

    def controller_by_ddp_id(self, ddp_id: int) -> Optional[Controller]:
        for c in self.controllers:
            if c.ddp_id == ddp_id:
                return c
        return None

    # ---- loading -------------------------------------------------------

    @staticmethod
    def load(path: str | Path) -> "Wall":
        path = Path(path)
        raw = path.read_bytes()
        doc = yaml.safe_load(raw)
        wall = Wall.from_dict(doc)
        wall.source_path = path
        wall.digest = hashlib.sha256(raw).hexdigest()[:12]
        return wall

    @staticmethod
    def from_dict(doc: dict) -> "Wall":
        try:
            w = int(doc["wall"]["width"])
            h = int(doc["wall"]["height"])
        except (KeyError, TypeError) as exc:
            raise GeometryError(f"wall.width / wall.height missing: {exc}") from exc

        panel = doc.get("panel") or {}
        pw = int(panel.get("width", 16))
        ph = int(panel.get("height", 16))
        if w % pw or h % ph:
            raise GeometryError(
                f"wall {w}x{h} is not a whole number of {pw}x{ph} panels"
            )
        chain = ChainSpec.from_dict(panel.get("chain"))

        color_order = str(doc.get("color_order", "GRB")).upper()
        if color_order not in COLOR_ORDERS:
            raise GeometryError(
                f"color_order must be one of {sorted(COLOR_ORDERS)}, got {color_order!r}"
            )

        r = doc.get("render") or {}
        render = RenderSpec(
            fps=int(r.get("fps", 30)),
            gamma=float(r.get("gamma", 2.2)),
            brightness=float(r.get("brightness", 0.5)),
            dither=str(r.get("dither", "bayer8")).lower(),
            epoch=float(r.get("epoch", 1767225600)),
        )
        if not 0.0 <= render.brightness <= 1.0:
            raise GeometryError(f"render.brightness must be 0..1, got {render.brightness}")
        if render.fps <= 0:
            raise GeometryError(f"render.fps must be positive, got {render.fps}")
        if render.dither not in ("bayer8", "none"):
            raise GeometryError(f"render.dither must be bayer8 or none, got {render.dither!r}")

        n = doc.get("network") or {}
        net = NetworkSpec(
            broadcast=str(n.get("broadcast", "192.168.50.255")),
            ddp_port=int(n.get("ddp_port", 4048)),
            control_port=int(n.get("control_port", 4049)),
            pixels_per_packet=int(n.get("pixels_per_packet", 480)),
            id_mode=str(n.get("id_mode", "per_controller")).lower(),
        )
        if net.pixels_per_packet * 3 + 10 > 1472:
            raise GeometryError(
                f"network.pixels_per_packet={net.pixels_per_packet} makes a "
                f"{net.pixels_per_packet * 3 + 10}-byte packet; the W5500 does "
                "not fragment IP, so the ceiling is 1472"
            )
        if net.id_mode not in ("per_controller", "default"):
            raise GeometryError(f"network.id_mode must be per_controller or default")

        n_columns = w // pw
        n_rows = h // ph

        controllers: List[Controller] = []
        seen_columns, seen_ips, seen_ids = set(), set(), set()
        for entry in doc.get("controllers") or []:
            col = int(entry["column"])
            if not 0 <= col < n_columns:
                raise GeometryError(f"controller column {col} outside 0..{n_columns - 1}")
            if col in seen_columns:
                raise GeometryError(f"two controllers claim column {col}")
            seen_columns.add(col)

            ip = str(entry["ip"])
            # Two boards on one address is a commissioning mistake and shows up
            # as a dead column. A loopback address is not: that is how you point
            # the whole wall at the software sink on one host.
            if ip in seen_ips and not _is_loopback(ip):
                raise GeometryError(f"two controllers share ip {ip}")
            seen_ips.add(ip)

            ddp_id = int(entry.get("ddp_id", 1))
            if ddp_id in seen_ids:
                raise GeometryError(f"two controllers share ddp_id {ddp_id}")
            if not 1 <= ddp_id <= 249:
                raise GeometryError(f"ddp_id {ddp_id} outside the usable range 1..249")
            seen_ids.add(ddp_id)

            placements = [
                PanelPlacement(
                    row=int(p["row"]),
                    output=int(p["output"]),
                    transform=str(p.get("transform", "none")).lower(),
                )
                for p in entry.get("panels") or []
            ]
            _validate_placements(placements, n_rows, col)
            controllers.append(Controller(column=col, ip=ip, ddp_id=ddp_id, panels=placements))

        if not controllers:
            raise GeometryError("no controllers defined")
        missing = sorted(set(range(n_columns)) - seen_columns)
        if missing:
            raise GeometryError(f"no controller defined for column(s) {missing}")

        wall = Wall(
            width=w, height=h, panel_w=pw, panel_h=ph, chain=chain,
            color_order=color_order, render=render, network=net,
            controllers=controllers,
        )
        for c in controllers:
            c.src_index = wall._build_index(c)
        return wall

    # ---- index construction --------------------------------------------

    def _build_index(self, ctrl: Controller) -> np.ndarray:
        base = chain_map(self.panel_w, self.panel_h, self.chain)
        n_slots = OUTPUTS_PER_CONTROLLER * self.panel_pixels
        # -1 means "no panel on this output": send black, never leave it stale.
        idx = np.full(n_slots, -1, dtype=np.int32)

        for p in ctrl.panels:
            local = apply_transform(base, self.panel_w, self.panel_h, p.transform)
            lx = local % self.panel_w
            ly = local // self.panel_w
            gx = ctrl.column * self.panel_w + lx
            gy = p.row * self.panel_h + ly
            slot = (p.output - 1) * self.panel_pixels
            idx[slot : slot + self.panel_pixels] = gy * self.width + gx

        return idx

    # ---- reporting -----------------------------------------------------

    def describe(self) -> str:
        lines = [
            f"wall {self.width}x{self.height} "
            f"({self.n_columns} cols x {self.n_rows} rows of "
            f"{self.panel_w}x{self.panel_h})",
            f"chain axis={self.chain.axis} start={self.chain.start} "
            f"serpentine={self.chain.serpentine}  colour={self.color_order}",
            f"render {self.render.fps} fps gamma={self.render.gamma} "
            f"brightness={self.render.brightness} dither={self.render.dither}",
            f"network ddp={self.network.ddp_port} bcast={self.network.broadcast} "
            f"{self.network.pixels_per_packet} px/packet "
            f"({self.network.pixels_per_packet * 3 + 10} bytes) id={self.network.id_mode}",
        ]
        for c in self.controllers:
            unmapped = int((c.src_index < 0).sum()) // self.panel_pixels
            lines.append(
                f"  col {c.column}  {c.ip}  ddp_id={c.ddp_id}  "
                f"{c.n_pixels} px / {c.n_bytes} B"
                + (f"  ({unmapped} output(s) unused)" if unmapped else "")
            )
        return "\n".join(lines)

    def coverage(self) -> Dict[str, int]:
        """How many wall pixels are driven, and how many twice."""
        counts = np.zeros(self.width * self.height, dtype=np.int32)
        for c in self.controllers:
            live = c.src_index[c.src_index >= 0]
            np.add.at(counts, live, 1)
        return {
            "total": int(counts.size),
            "driven": int((counts > 0).sum()),
            "unmapped": int((counts == 0).sum()),
            "duplicated": int((counts > 1).sum()),
        }


def _is_loopback(ip: str) -> bool:
    try:
        import ipaddress
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _validate_placements(placements: Sequence[PanelPlacement], n_rows: int, col: int) -> None:
    if not placements:
        raise GeometryError(f"column {col}: no panels listed")
    outs, rows = set(), set()
    for p in placements:
        if not 1 <= p.output <= OUTPUTS_PER_CONTROLLER:
            raise GeometryError(
                f"column {col} row {p.row}: output {p.output} outside 1..{OUTPUTS_PER_CONTROLLER}"
            )
        if p.output in outs:
            raise GeometryError(f"column {col}: output D{p.output} used twice")
        outs.add(p.output)
        if not 0 <= p.row < n_rows:
            raise GeometryError(f"column {col}: row {p.row} outside 0..{n_rows - 1}")
        if p.row in rows:
            raise GeometryError(f"column {col}: row {p.row} listed twice")
        rows.add(p.row)
        if p.transform not in TRANSFORMS:
            raise GeometryError(
                f"column {col} row {p.row}: transform {p.transform!r} not in {TRANSFORMS}"
            )
    missing = sorted(set(range(n_rows)) - rows)
    if missing:
        raise GeometryError(f"column {col}: no panel mapped for row(s) {missing}")
