import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64
CX     = WIDTH  // 2
CY     = HEIGHT // 2
CHIP_HALF = 4

# Sub-nodes: smaller relay squares placed around the main chip
# Each: (centre_x, centre_y, half_size)
_NODES = [
    (20, 20, 2),   # top-left relay
    (44, 18, 2),   # top-right relay
    (18, 46, 2),   # bottom-left relay
    (46, 46, 2),   # bottom-right relay
    (32, 14, 2),   # top centre relay
    (32, 50, 2),   # bottom centre relay
]

# Traces: list of waypoint lists. Some go chip→node, some node→edge, some chip→edge
_RAW_TRACES = [
    # chip → top-left node
    [(CX - CHIP_HALF, CY - 3), (20, CY - 3), (20, 20)],
    # chip → top-right node
    [(CX + CHIP_HALF, CY - 2), (44, CY - 2), (44, 18)],
    # chip → bottom-left node
    [(CX - CHIP_HALF, CY + 3), (18, CY + 3), (18, 46)],
    # chip → bottom-right node
    [(CX + CHIP_HALF, CY + 2), (46, CY + 2), (46, 46)],
    # chip → top centre node
    [(CX, CY - CHIP_HALF), (CX, 14)],
    # chip → bottom centre node
    [(CX, CY + CHIP_HALF), (CX, 50)],

    # top-left node → edges
    [(20, 20), (20,  8), (0,   8)],
    [(20, 20), (8,  20), (8,   0)],
    # top-right node → edges
    [(44, 18), (44,  6), (63,  6)],
    [(44, 18), (56, 18), (56,  0)],
    # bottom-left node → edges
    [(18, 46), (18, 58), (0,  58)],
    [(18, 46), (6,  46), (6,  63)],
    # bottom-right node → edges
    [(46, 46), (46, 56), (63, 56)],
    [(46, 46), (58, 46), (58, 63)],
    # top-centre node → edges
    [(CX, 14), (20, 14), (20,  0)],
    [(CX, 14), (44, 14), (44,  0)],
    # bottom-centre node → edges
    [(CX, 50), (14, 50), (14, 63)],
    [(CX, 50), (50, 50), (50, 63)],

    # Direct chip → edge traces (bypassing nodes)
    [(CX + CHIP_HALF, CY - 1), (58, CY - 1), (63, CY - 1)],
    [(CX - CHIP_HALF, CY + 1), (10, CY + 1), (0,  CY + 1)],
]

_COLORS = [
    (0,   255,  80),   # neon green
    (0,   220, 255),   # cyan
    (0,   160, 255),   # blue-cyan
    (40,   80, 255),   # electric blue
    (0,   255, 180),   # teal
]


def _rasterise(waypoints):
    pixels = []
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        steps = max(abs(x1 - x0), abs(y1 - y0))
        for s in range(steps + 1):
            t  = s / steps if steps else 0
            px = int(round(x0 + (x1 - x0) * t))
            py = int(round(y0 + (y1 - y0) * t))
            if not pixels or pixels[-1] != (px, py):
                pixels.append((px, py))
    return pixels


_TRACES = [_rasterise(wp) for wp in _RAW_TRACES]
_N = len(_TRACES)


# Build a set of node pixel regions for bloom detection
def _node_pixels(nx, ny, nh):
    pts = set()
    for dy in range(-nh, nh + 1):
        for dx in range(-nh, nh + 1):
            pts.add((nx + dx, ny + dy))
    return pts

_NODE_PIXEL_SETS = [_node_pixels(nx, ny, nh) for nx, ny, nh in _NODES]


class _Flash:
    def __init__(self, trace_idx: int):
        self.pixels = _TRACES[trace_idx]
        self.color  = random.choice(_COLORS)
        self.bright = 1.0
        self.decay  = random.uniform(1.0, 2.5)


class PcbTraces(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "PCB Traces",
            "description": "Circuit board — paths flash from chip through relay nodes out to edges",
            "category": "ambient",
        }

    def __init__(self):
        self._speed       = 5
        self._t           = 0.0
        self._flashes: list[_Flash] = []
        self._spawn_timer = 0.0

    def start(self) -> None:
        self._t           = 0.0
        self._flashes     = []
        self._spawn_timer = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        self._t += dt
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        speed_mul = 0.5 + self._speed * 0.10

        self._spawn_timer -= dt
        if self._spawn_timer <= 0:
            # Spawn 2–4 simultaneous flashes on different traces
            batch = random.randint(2, 4)
            indices = random.sample(range(_N), min(batch, _N))
            for ti in indices:
                self._flashes.append(_Flash(ti))
            self._spawn_timer = random.uniform(0.10, 0.30) / speed_mul

        for f in self._flashes:
            f.bright = max(0.0, f.bright - f.decay * dt)
        self._flashes = [f for f in self._flashes if f.bright > 0.02]

        # Draw flashes
        node_boost: dict[int, float] = {}   # node_idx → max brightness hitting it
        for f in self._flashes:
            cr, cg, cb = f.color
            b  = f.bright
            rv = int(cr * b); gv = int(cg * b); bv = int(cb * b)
            for (tx, ty) in f.pixels:
                if not (0 <= tx < WIDTH and 0 <= ty < HEIGHT):
                    continue
                cur = frame[ty, tx]
                frame[ty, tx] = (max(cur[0], rv), max(cur[1], gv), max(cur[2], bv))
                # Check if this pixel hits a relay node
                for ni, nset in enumerate(_NODE_PIXEL_SETS):
                    if (tx, ty) in nset:
                        node_boost[ni] = max(node_boost.get(ni, 0.0), b)

        # Draw relay nodes (dim always, brighten when hit by a flash)
        for ni, (nx, ny, nh) in enumerate(_NODES):
            boost  = node_boost.get(ni, 0.0)
            base_g = 25
            bright_g = int(base_g + (200 - base_g) * boost)
            bright_c = int(80 * boost)
            for dy in range(-nh, nh + 1):
                for dx in range(-nh, nh + 1):
                    px, py = nx + dx, ny + dy
                    if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
                        continue
                    border = (abs(dx) == nh or abs(dy) == nh)
                    m = 1.0 if border else 0.3
                    cur = frame[py, px]
                    frame[py, px] = (
                        max(cur[0], 0),
                        max(cur[1], int(bright_g * m)),
                        max(cur[2], int(bright_c * m)),
                    )

        # Main chip — pulsing glow
        chip_p = 0.55 + 0.45 * math.sin(self._t * 2.8)
        for dy in range(-CHIP_HALF, CHIP_HALF + 1):
            for dx in range(-CHIP_HALF, CHIP_HALF + 1):
                px, py = CX + dx, CY + dy
                if not (0 <= px < WIDTH and 0 <= py < HEIGHT):
                    continue
                border = (abs(dx) == CHIP_HALF or abs(dy) == CHIP_HALF)
                m = chip_p if border else chip_p * 0.25
                cur = frame[py, px]
                frame[py, px] = (max(cur[0], 0), max(cur[1], int(200 * m)), max(cur[2], int(80 * m)))

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = max(1, min(10, int(value)))
