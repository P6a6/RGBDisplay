import math
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64


class Plasma(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Plasma",
            "description": "Smooth flowing plasma cycling through every colour with high contrast",
            "category": "ambient",
        }

    def __init__(self):
        self._speed = 5
        self._t     = 0.0
        xs = np.linspace(0, 2 * math.pi, WIDTH,  endpoint=False)
        ys = np.linspace(0, 2 * math.pi, HEIGHT, endpoint=False)
        self._gx, self._gy = np.meshgrid(xs, ys)

    def start(self) -> None:
        self._t = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        rate    = 0.35 + self._speed * 0.10
        self._t += dt * rate

        t  = self._t
        gx = self._gx
        gy = self._gy

        # Several overlapping waves at different scales / angles
        v  =  np.sin(gx * 1.0 + t)
        v +=  np.sin(gy * 0.8 + t * 1.4)
        v +=  np.sin((gx + gy) * 0.6 + t * 0.9)
        dist = np.sqrt((gx - math.pi) ** 2 + (gy - math.pi) ** 2)
        v +=  np.sin(dist * 1.2 - t * 1.2)

        # Normalise to [0, 1] → full hue cycle
        hue = (v / 8.0 + 0.5).astype(np.float32)   # centred, ~0–1

        # HSV (hue, S=1, V=1) → RGB via sector decomposition
        h6 = (hue * 6.0).astype(np.float32)
        i  = h6.astype(np.int32) % 6
        f  = (h6 - np.floor(h6)).astype(np.float32)

        ones = np.ones((HEIGHT, WIDTH), dtype=np.float32)
        zero = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        q    = 1.0 - f
        # Sector-based RGB (S=V=1)
        r_f = np.choose(i, [ones, q,    zero, zero, f,    ones])
        g_f = np.choose(i, [f,    ones, ones, q,    zero, zero])
        b_f = np.choose(i, [zero, zero, f,    ones, ones, q   ])

        # Brightness envelope: dark valleys between colour bands → high contrast
        bright = (np.abs(np.sin(v * (math.pi / 4.0))) ** 0.6).astype(np.float32)
        bright = np.clip(bright * 1.1, 0.0, 1.0)

        r_out = np.clip(r_f * bright * 255, 0, 255).astype(np.uint8)
        g_out = np.clip(g_f * bright * 255, 0, 255).astype(np.uint8)
        b_out = np.clip(b_f * bright * 255, 0, 255).astype(np.uint8)

        return np.stack([r_out, g_out, b_out], axis=-1)

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = max(1, min(10, int(value)))
