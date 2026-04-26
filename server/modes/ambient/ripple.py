import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64

# Pre-compute per-pixel (x, y) grids for fast distance calculation
_X = np.arange(WIDTH,  dtype=np.float32)[np.newaxis, :]   # (1, W)
_Y = np.arange(HEIGHT, dtype=np.float32)[:, np.newaxis]   # (H, 1)

MAX_RIPPLES = 6
RIPPLE_LIFE = 3.2    # seconds until a ripple fades out


class _Ripple:
    __slots__ = ('cx', 'cy', 'age', 'speed', 'wavelength', 'amp')

    def __init__(self):
        self.cx         = random.uniform(8, WIDTH  - 8)
        self.cy         = random.uniform(8, HEIGHT - 8)
        self.age        = 0.0
        self.speed      = random.uniform(10, 20)     # px / s (ring expansion)
        self.wavelength = random.uniform(5.0, 10.0)  # px between crests
        self.amp        = random.uniform(0.6, 1.0)

    @property
    def done(self):
        return self.age >= RIPPLE_LIFE


class Ripple(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Ripple",
            "description": "Circular water ripples interfering on a deep blue surface",
            "category": "ambient",
        }

    def __init__(self):
        self._speed_setting = 5
        self._t             = 0.0
        self._ripples: list[_Ripple] = []
        self._spawn_timer   = 0.0

    def start(self) -> None:
        self._t           = 0.0
        self._ripples     = []
        self._spawn_timer = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        speed_mul = 0.5 + self._speed_setting * 0.10
        self._t  += dt * speed_mul

        # Age and cull
        for r in self._ripples:
            r.age += dt * speed_mul
        self._ripples = [r for r in self._ripples if not r.done]

        # Spawn
        self._spawn_timer -= dt * speed_mul
        if self._spawn_timer <= 0 and len(self._ripples) < MAX_RIPPLES:
            self._ripples.append(_Ripple())
            self._spawn_timer = random.uniform(0.5, 1.4)

        # Accumulate wave height at every pixel
        wave = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        for r in self._ripples:
            dist = np.sqrt((_X - r.cx) ** 2 + (_Y - r.cy) ** 2)
            radius  = r.speed * r.age
            # Envelope: Gaussian centred on expanding ring
            env = np.exp(-0.5 * ((dist - radius) / (r.wavelength * 0.8)) ** 2)
            # Fade out as ripple ages
            fade = max(0.0, 1.0 - r.age / RIPPLE_LIFE) ** 1.5
            wave += env * fade * r.amp * np.cos((dist - radius) * (2 * math.pi / r.wavelength))

        # Normalise to [-1, 1]
        wave = np.clip(wave, -1.0, 1.0)

        # Map wave height → colour on a deep blue/teal palette
        # Positive crest: bright cyan/white  |  trough: dark blue
        val = (wave + 1.0) * 0.5   # 0–1

        r_ch = (val * 30).astype(np.uint8)
        g_ch = (val * 160 + 30).clip(0, 255).astype(np.uint8)
        b_ch = (val * 100 + 100).clip(0, 255).astype(np.uint8)

        return np.stack([r_ch, g_ch, b_ch], axis=-1)

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed_setting}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed_setting = max(1, min(10, int(value)))
