import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64
NUM_STARS = 60

# (r_base, r_var, g_base, g_var, b_base, b_var) — varied warm palette
_PALETTES = [
    (255, 0,   200, 30,  0,   0),    # gold
    (255, 0,   160, 20,  0,   0),    # amber
    (255, 0,   110, 20,  0,   0),    # orange
    (255, 0,    80,  0,  0,   0),    # red-orange
    (255, 0,   230, 10,  60,  0),    # warm white
    (255, 0,   190, 40,  20,  0),    # golden-orange
]


class _Star:
    __slots__ = ('x', 'y', 'speed', 'base_bright', 'twinkle_hz', 'phase', 'size', 'palette')

    def spawn(self, at_top: bool = False):
        self.x           = random.uniform(0, WIDTH - 1)
        self.y           = random.uniform(-6, 0) if at_top else random.uniform(0, HEIGHT)
        self.speed       = random.uniform(4, 20)
        self.base_bright = random.uniform(0.55, 1.0)
        self.twinkle_hz  = random.uniform(0.4, 1.8)
        self.phase       = random.uniform(0, math.tau)
        self.size        = random.choices([1, 2], weights=[4, 1])[0]
        self.palette     = random.choice(_PALETTES)


class StarRain(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Star Rain",
            "description": "Warm twinkling stars — gold, amber, orange hues drifting down",
            "category": "ambient",
        }

    def __init__(self):
        self._speed_setting = 5
        self._t   = 0.0
        self._stars: list[_Star] = []
        self._reset()

    def _reset(self):
        self._stars = []
        for _ in range(NUM_STARS):
            s = _Star()
            s.spawn(at_top=False)
            self._stars.append(s)

    def start(self) -> None:
        self._reset()
        self._t = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        self._t += dt
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        speed_mul = 0.4 + self._speed_setting * 0.14

        for s in self._stars:
            s.y += s.speed * speed_mul * dt
            if s.y >= HEIGHT:
                s.spawn(at_top=True)
                continue

            b = s.base_bright * (0.85 + 0.15 * math.sin(s.twinkle_hz * self._t * math.tau + s.phase))
            b = max(0.0, b)

            rb, rv, gb, gv, bb, bv = s.palette
            r  = int(min(255, (rb + rv * s.base_bright) * b))
            g  = int(min(255, (gb + gv * s.base_bright) * b))
            bc = int(min(255, (bb + bv * s.base_bright) * b))

            ix, iy = int(s.x), int(s.y)

            if s.size == 2 and 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                for dx, dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = ix + dx, iy + dy
                    fade = 1.0 if (dx == 0 and dy == 0) else 0.35
                    if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                        cur = frame[ny, nx]
                        frame[ny, nx] = (
                            max(cur[0], int(r  * fade)),
                            max(cur[1], int(g  * fade)),
                            max(cur[2], int(bc * fade)),
                        )
            elif 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                cur = frame[iy, ix]
                frame[iy, ix] = (max(cur[0], r), max(cur[1], g), max(cur[2], bc))

            # Faint tail (1 px above)
            ty = iy - 1
            if 0 <= ty < HEIGHT and 0 <= ix < WIDTH:
                fade = b * 0.18
                cur  = frame[ty, ix]
                frame[ty, ix] = (max(cur[0], int(r*fade)), max(cur[1], int(g*fade)), max(cur[2], int(bc*fade)))

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed_setting}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed_setting = max(1, min(10, int(value)))
