import math
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64


class NeonLines(BaseMode):
    """Aurora Borealis — overlapping colour curtains that undulate and breathe."""

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Aurora",
            "description": "Northern lights — shifting colour curtains with dynamic hue and rhythm",
            "category": "ambient",
        }

    def __init__(self):
        self._speed = 4
        self._t     = 0.0

        self._x = np.arange(WIDTH,  dtype=np.float32)[np.newaxis, :]
        self._y = np.arange(HEIGHT, dtype=np.float32)[:, np.newaxis]

        # (base_y_frac, amp_frac, drift_spd, wave_spd2, R, G, B)
        self._curtains = [
            (0.18, 0.14, 0.41, 0.70, 0,   255, 120),   # bright green, high
            (0.32, 0.18, 0.29, 1.10, 0,   180, 255),   # cyan-blue
            (0.48, 0.13, 0.55, 0.85, 60,  80,  255),   # violet, mid
            (0.62, 0.10, 0.68, 1.30, 0,   220, 160),   # teal, lower
            (0.25, 0.08, 0.90, 0.60, 140, 0,   200),   # magenta accent
            (0.55, 0.12, 0.35, 1.50, 0,   140, 255),   # ice blue
        ]

    def start(self) -> None:
        self._t = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        rate    = 0.35 + self._speed * 0.07
        self._t += dt * rate

        t  = self._t
        x  = self._x
        y  = self._y
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.float32)

        for base_f, amp_f, spd, spd2, cr, cg, cb in self._curtains:
            base_y = HEIGHT * base_f
            amp    = HEIGHT * amp_f

            cy = (base_y
                  + amp       * np.sin(x * 0.16 + t * spd)
                  + amp * 0.50 * np.sin(x * 0.38 + t * spd2)
                  + amp * 0.22 * np.sin(x * 0.07 + t * spd * 0.38))

            bw = 4.5 + 4.0 * np.sin(x * 0.20 + t * 0.18)
            bw = np.maximum(bw, 1.0)

            brightness = np.exp(-0.5 * ((y - cy) / bw) ** 2)

            # Each curtain breathes independently
            pulse = 0.72 + 0.28 * math.sin(t * spd * 0.5 + base_f * math.tau)

            frame[:, :, 0] += brightness * cr * pulse
            frame[:, :, 1] += brightness * cg * pulse
            frame[:, :, 2] += brightness * cb * pulse

        return np.clip(frame, 0, 255).astype(np.uint8)

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = max(1, min(10, int(value)))
