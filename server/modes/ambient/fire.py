import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64

def _build_palette() -> np.ndarray:
    pal = np.zeros((256, 3), dtype=np.uint8)
    stops = [
        (0,   (0,   0,   0)),
        (55,  (80,  0,   0)),
        (105, (180, 20,  0)),
        (155, (255, 80,  0)),
        (195, (255, 160, 0)),
        (225, (255, 220, 30)),
        (255, (255, 255, 240)),
    ]
    for i in range(len(stops) - 1):
        i0, c0 = stops[i]
        i1, c1 = stops[i + 1]
        for idx in range(i0, i1 + 1):
            t = (idx - i0) / (i1 - i0)
            pal[idx] = [int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3)]
    return pal

_PALETTE = _build_palette()

_X  = np.arange(WIDTH, dtype=np.float32)
_CX = WIDTH / 2.0
_EDGE_COOL = 0.014 * (np.abs(_X - _CX) / _CX) ** 1.6


class Fire(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Fire",
            "description": "Shaped flame rising tall — breathes in height and sways sideways",
            "category": "ambient",
        }

    def __init__(self):
        self._intensity = 5
        self._t = 0.0
        self._heat = np.zeros((HEIGHT + 2, WIDTH), dtype=np.float32)
        self._sparkles: list[list] = []   # [x, y, vy, life, r, g]
        self._prev_breath = 0.65

    def start(self) -> None:
        self._heat[:] = 0.0
        self._t = 0.0
        self._sparkles = []
        self._prev_breath = 0.65

    def stop(self) -> None:
        pass

    def _breath(self) -> float:
        b = 0.5 * math.sin(self._t * 0.55) + 0.35 * math.sin(self._t * 1.25)
        return max(0.30, min(1.0, 0.65 + 0.35 * b))

    def _heat_mask(self) -> np.ndarray:
        cx = _CX + math.sin(self._t * 1.1) * 4.5
        # Narrower main Gaussian (sigma 6 instead of 9) → pointier base
        main  = np.exp(-0.5 * ((_X - cx)           /  6.0) ** 2)
        left  = np.exp(-0.5 * ((_X - cx + 10.0 + math.sin(self._t * 2.0) * 3) / 4.5) ** 2) * 0.50
        right = np.exp(-0.5 * ((_X - cx - 10.0 + math.sin(self._t * 1.6) * 3) / 4.5) ** 2) * 0.50
        return np.clip(main + left + right, 0.0, 1.0)

    def _step(self) -> None:
        self._t += 1.0 / 30.0
        breath   = self._breath()
        # Stronger heat source so flame reaches much higher
        strength = (0.72 + self._intensity * 0.08) * breath

        mask   = self._heat_mask()
        self._heat[HEIGHT]     = np.clip(mask * np.random.uniform(0.85, 1.00, WIDTH) * strength, 0, 1)
        self._heat[HEIGHT + 1] = np.clip(mask * np.random.uniform(0.60, 0.92, WIDTH) * strength, 0, 1)

        below1 = self._heat[1:HEIGHT + 1]
        below2 = self._heat[2:HEIGHT + 2]
        left   = np.roll(below1,  1, axis=1)
        right  = np.roll(below1, -1, axis=1)

        # Lower cooling so heat travels farther up
        base_cool = (0.014 - self._intensity * 0.0010) * (1.5 - 0.5 * breath)
        cooling   = base_cool + _EDGE_COOL

        new = left * 0.20 + below1 * 0.44 + right * 0.20 + below2 * 0.16 - cooling
        self._heat[:HEIGHT] = np.maximum(0.0, new)

    def _spawn_sparkles(self, breath: float):
        surge = breath - self._prev_breath
        count = 0
        if surge > 0.03:
            count = random.randint(6, 14)
        elif random.random() < 0.25:
            count = random.randint(2, 5)
        cx = _CX + math.sin(self._t * 1.1) * 4.5
        for _ in range(count):
            # Wide spread — sparkles escape the flame area
            sx = cx + random.uniform(-22, 22)
            col = int(max(0, min(WIDTH - 1, sx)))
            top_y = HEIGHT - 1
            for row in range(HEIGHT):
                if self._heat[row, col] > 0.08:
                    top_y = row
                    break
            sy = float(top_y + random.randint(-4, 3))
            # Fast enough to reach the top of the display
            vy    = random.uniform(-35, -10)
            life  = random.uniform(0.6, 1.8)
            r     = random.randint(200, 255)
            g     = random.randint(30, 130)
            self._sparkles.append([sx, sy, vy, life, r, g])
        self._prev_breath = breath

    def tick(self, dt: float) -> np.ndarray:
        breath = self._breath()
        self._spawn_sparkles(breath)

        for _ in range(max(1, round(dt * 30))):
            self._step()

        indices = np.clip((self._heat[:HEIGHT] * 255).astype(np.int32), 0, 255)
        frame = _PALETTE[indices].copy()

        # Update and draw sparkles — allowed to travel full display height
        alive = []
        for sp in self._sparkles:
            sx, sy, vy, life, r, g = sp
            sy  += vy * dt
            life -= dt * 0.9   # slower fade so they travel farther
            ix, iy = int(sx), int(sy)
            if life > 0 and 0 <= iy < HEIGHT and 0 <= ix < WIDTH:
                fade = min(1.0, life)
                pr, pg = int(r * fade), int(g * fade)
                frame[iy, ix] = (
                    max(frame[iy, ix, 0], pr),
                    max(frame[iy, ix, 1], pg),
                    frame[iy, ix, 2],
                )
                sp[1] = sy
                sp[3] = life
                alive.append(sp)
            elif life > 0 and -4 <= iy < HEIGHT:
                # Still alive but off-screen top — keep tracking
                sp[1] = sy
                sp[3] = life
                alive.append(sp)
        self._sparkles = alive[:120]   # cap so we never accumulate forever

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "intensity", "label": "Intensity", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._intensity}]

    def apply_setting(self, key: str, value) -> None:
        if key == "intensity":
            self._intensity = max(1, min(10, int(value)))
