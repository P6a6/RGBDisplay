import numpy as np
from base_mode import BaseMode


class RainbowScroll(BaseMode):
    def __init__(self):
        self._offset = 0.0
        self._speed  = 20.0   # pixels per second (diagonal)

        # Pre-build 2D index grids so tick() is pure numpy
        x = np.arange(64, dtype=np.float32)[np.newaxis, :]   # (1, 64)
        y = np.arange(64, dtype=np.float32)[:, np.newaxis]   # (64, 1)
        # Diagonal index: normalise (x+y) over the range 0–127 to get hue 0–1
        self._xy = x + y   # shape (64, 64), values 0–126

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Rainbow Scroll",
            "description": "Full-spectrum rainbow scrolling diagonally across the display",
            "category": "ambient",
        }

    def start(self) -> None:
        self._offset = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        self._offset = (self._offset + self._speed * dt) % 128.0

        # Hue in [0, 1) for every pixel — diagonal pattern
        h = ((self._xy + self._offset) % 128.0) / 128.0

        h6 = (h * 6.0).astype(np.float32)
        i  = h6.astype(np.int32) % 6
        f  = (h6 - np.floor(h6)).astype(np.float32)

        ones = np.ones((64, 64), dtype=np.float32)
        zero = np.zeros((64, 64), dtype=np.float32)
        q    = 1.0 - f

        r = np.choose(i, [ones, q,    zero, zero, f,    ones])
        g = np.choose(i, [f,    ones, ones, q,    zero, zero])
        b = np.choose(i, [zero, zero, f,    ones, ones, q   ])

        return np.stack([
            (r * 255).astype(np.uint8),
            (g * 255).astype(np.uint8),
            (b * 255).astype(np.uint8),
        ], axis=-1)

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 120, "step": 1, "value": int(self._speed)}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = float(value)
