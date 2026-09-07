import numpy as np
import pytest

from baybasi.geometry import Wall

WALL_DOC = {
    "wall": {"width": 64, "height": 192},
    "panel": {"width": 16, "height": 16,
              "chain": {"axis": "column", "start": "top_left", "serpentine": True}},
    "color_order": "RGB",
    "render": {"fps": 30, "gamma": 2.2, "brightness": 1.0, "dither": "none",
               "epoch": 1767225600},
    "network": {"broadcast": "127.0.0.1", "ddp_port": 14048,
                "pixels_per_packet": 480, "id_mode": "per_controller"},
    "controllers": [
        {"column": c, "ip": "127.0.0.1", "ddp_id": 10 + c,
         "panels": [{"row": r, "output": r + 1} for r in range(12)]}
        for c in range(4)
    ],
}


@pytest.fixture
def wall():
    import copy
    return Wall.from_dict(copy.deepcopy(WALL_DOC))


@pytest.fixture
def frame(wall):
    rng = np.random.default_rng(1234)
    return rng.integers(0, 256, (wall.height, wall.width, 3), dtype=np.uint8)
