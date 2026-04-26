import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64

# Trail colour at full brightness: pure neon green, no red/blue bleed
_TRAIL_R = 0
_TRAIL_G = 255
_TRAIL_B = 70

# Head pixel colour
_HEAD = np.array([200, 255, 200], dtype=np.uint8)


class MatrixRain(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Matrix Rain",
            "description": "Classic digital rain columns in neon green",
            "category": "ambient",
        }

    def __init__(self):
        self._speed = 5
        self._reset()

    def _col_speed(self) -> float:
        base = 10 + self._speed * 3.5   # 13.5–45 px/s
        return base * random.uniform(0.6, 1.4)

    def _reset(self):
        self._heads  = np.array([random.uniform(0, HEIGHT) for _ in range(WIDTH)], dtype=np.float32)
        self._speeds = np.array([self._col_speed() for _ in range(WIDTH)],         dtype=np.float32)
        self._trails = np.zeros((HEIGHT, WIDTH), dtype=np.float32)

    def start(self) -> None:
        self._reset()

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        # Decay all trail brightness
        self._trails *= 0.80

        # Advance each column's head
        self._heads += self._speeds * dt

        # Wrap columns that go off-screen
        for col in np.where(self._heads >= HEIGHT)[0]:
            self._heads[col] = random.uniform(-HEIGHT * 0.4, 0)
            self._speeds[col] = self._col_speed()

        # Stamp head positions into trail map
        for col in range(WIDTH):
            hy = int(self._heads[col])
            if 0 <= hy < HEIGHT:
                self._trails[hy, col] = 1.0

        # Build RGB frame via vectorised palette lookup
        # trail value v → R=0, G=v*255, B=v*70
        v = self._trails   # (H, W) float32, 0–1
        r_ch = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
        g_ch = np.clip(v * 255, 0, 255).astype(np.uint8)
        b_ch = np.clip(v *  70, 0, 255).astype(np.uint8)
        frame = np.stack([r_ch, g_ch, b_ch], axis=-1)

        # Overwrite head pixels with bright near-white
        for col in range(WIDTH):
            hy = int(self._heads[col])
            if 0 <= hy < HEIGHT:
                frame[hy, col] = _HEAD

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = max(1, min(10, int(value)))
            self._speeds = np.array([self._col_speed() for _ in range(WIDTH)], dtype=np.float32)
