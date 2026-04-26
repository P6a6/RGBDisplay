import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64
CX     = WIDTH  / 2.0
CY     = HEIGHT / 2.0

NUM_STARS  = 130
TRAIL_LEN  = 8


class Star:
    __slots__ = ('x', 'y', 'z', 'trail')

    def __init__(self):
        self.reset(initial=True)

    def reset(self, initial: bool = False):
        self.x     = random.uniform(-1.0, 1.0)
        self.y     = random.uniform(-1.0, 1.0)
        self.z     = random.uniform(0.55, 1.0) if initial else 1.0
        self.trail = []


class Starfield(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Starfield",
            "description": "Warp-speed stars with glowing trails — drifting vanishing point for banking feel",
            "category": "ambient",
        }

    def __init__(self):
        self._speed = 5
        self._t     = 0.0
        self._stars = [Star() for _ in range(NUM_STARS)]

    def start(self) -> None:
        self._t     = 0.0
        self._stars = [Star() for _ in range(NUM_STARS)]

    def stop(self) -> None:
        pass

    def _star_color(self, z: float, brightness: float):
        t = max(0.0, min(1.0, 1.0 - z))
        r = int((180 + 75 * t) * brightness)
        g = int((190 + 65 * t) * brightness)
        b = int((255 - 55 * t) * brightness)
        return (min(255, r), min(255, g), min(255, b))

    def tick(self, dt: float) -> np.ndarray:
        self._t += dt
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        # Slowly drifting vanishing point — feels like banking through space
        vp_x = CX + math.sin(self._t * 0.25) * 10.0
        vp_y = CY + math.sin(self._t * 0.18) * 7.0

        # Speed oscillates subtly so there are slow/fast moments
        speed_osc = 0.85 + 0.15 * math.sin(self._t * 0.40)
        warp = (0.20 + self._speed * 0.11) * speed_osc

        for star in self._stars:
            star.z -= warp * dt
            if star.z <= 0.015:
                star.reset()
                continue

            sx = int(vp_x + star.x / star.z * CX)
            sy = int(vp_y + star.y / star.z * CY)

            if not (0 <= sx < WIDTH and 0 <= sy < HEIGHT):
                star.reset()
                continue

            proximity  = 1.0 - star.z
            brightness = min(1.0, proximity ** 1.1 + 0.05)

            star.trail.append((sx, sy))
            if len(star.trail) > TRAIL_LEN:
                star.trail = star.trail[-TRAIL_LEN:]

            n = len(star.trail)
            for idx, (tx, ty) in enumerate(star.trail):
                is_head = (idx == n - 1)
                trail_bright = brightness if is_head else brightness * (idx + 1) / n * 0.55
                r, g, b = self._star_color(star.z, trail_bright)

                if is_head and star.z < 0.12:
                    for dy in range(-1, 2):
                        for dx in range(-1, 2):
                            nx, ny = tx + dx, ty + dy
                            if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                                cur = frame[ny, nx]
                                frame[ny, nx] = (max(cur[0], r), max(cur[1], g), max(cur[2], b))
                elif is_head and star.z < 0.28:
                    for ddx, ddy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
                        nx, ny = tx + ddx, ty + ddy
                        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                            cur = frame[ny, nx]
                            frame[ny, nx] = (max(cur[0], r), max(cur[1], g), max(cur[2], b))
                else:
                    if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                        cur = frame[ty, tx]
                        frame[ty, tx] = (max(cur[0], r), max(cur[1], g), max(cur[2], b))

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = max(1, min(10, int(value)))
