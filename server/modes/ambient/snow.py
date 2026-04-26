import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64
NUM_FLAKES = 60


class _Flake:
    __slots__ = ('x', 'y', 'speed', 'drift_amp', 'drift_hz', 'phase', 'bright', 'size')

    def spawn(self, at_top: bool = False):
        self.x         = random.uniform(0, WIDTH - 1)
        self.y         = random.uniform(-6, 0) if at_top else random.uniform(0, HEIGHT)
        self.speed     = random.uniform(3, 12)          # px / s downward
        self.drift_amp = random.uniform(0.4, 1.8)       # side-to-side amplitude
        self.drift_hz  = random.uniform(0.3, 0.9)       # drift frequency
        self.phase     = random.uniform(0, math.tau)
        self.bright    = random.uniform(0.55, 1.0)
        self.size      = random.choices([1, 2], weights=[5, 1])[0]


class Snow(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Snow",
            "description": "Gentle snowflakes drifting down, swaying softly side to side",
            "category": "ambient",
        }

    def __init__(self):
        self._speed_setting = 4
        self._t   = 0.0
        self._flakes: list[_Flake] = []
        self._reset()

    def _reset(self):
        self._flakes = []
        for _ in range(NUM_FLAKES):
            f = _Flake()
            f.spawn(at_top=False)
            self._flakes.append(f)

    def start(self) -> None:
        self._reset()
        self._t = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        self._t += dt
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        speed_mul = 0.3 + self._speed_setting * 0.10

        for f in self._flakes:
            # Gentle sinusoidal horizontal drift
            f.x += f.drift_amp * math.cos(f.drift_hz * self._t * math.tau + f.phase) * dt
            f.y += f.speed * speed_mul * dt

            # Wrap x softly
            f.x = f.x % WIDTH

            if f.y >= HEIGHT:
                f.spawn(at_top=True)
                continue

            # White with very slight blue tint — varies per flake
            b  = f.bright
            rv = int(min(255, 210 * b))
            gv = int(min(255, 225 * b))
            bv = int(min(255, 255 * b))

            ix, iy = int(f.x), int(f.y)

            if f.size == 2 and 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                # Small diamond / + shape for bigger flakes
                for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = ix + dx, iy + dy
                    fade = 1.0 if (dx == 0 and dy == 0) else 0.40
                    if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                        cur = frame[ny, nx]
                        frame[ny, nx] = (
                            max(cur[0], int(rv * fade)),
                            max(cur[1], int(gv * fade)),
                            max(cur[2], int(bv * fade)),
                        )
            elif 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
                cur = frame[iy, ix]
                frame[iy, ix] = (max(cur[0], rv), max(cur[1], gv), max(cur[2], bv))

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed_setting}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed_setting = max(1, min(10, int(value)))
