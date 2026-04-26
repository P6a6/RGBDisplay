import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64
MAX_METEORS = 18


def _hsv_to_rgb(h, s, v):
    h6 = h * 6.0
    i  = int(h6) % 6
    f  = h6 - math.floor(h6)
    p  = v * (1 - s)
    q  = v * (1 - s * f)
    t  = v * (1 - s * (1 - f))
    r, g, b = [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i]
    return (int(r * 255), int(g * 255), int(b * 255))


class _Meteor:
    def __init__(self, speed_mul: float):
        if random.random() < 0.5:
            self.x = random.uniform(0, WIDTH)
            self.y = -2.0
        else:
            self.x = -2.0
            self.y = random.uniform(0, HEIGHT * 0.6)

        angle      = random.uniform(math.radians(30), math.radians(70))
        self.speed = random.uniform(40, 110) * speed_mul
        self.vx    = math.cos(angle) * self.speed
        self.vy    = math.sin(angle) * self.speed
        self.tail  = random.randint(6, 18)
        h = random.choices([0.0, 0.55, 0.60, 0.10, 0.80], weights=[5, 3, 2, 1, 1])[0]
        s = random.uniform(0.0, 0.5) if h == 0.0 else random.uniform(0.5, 1.0)
        self.color  = _hsv_to_rgb(h, s, 1.0)
        self.bright = random.uniform(0.7, 1.0)
        self.history = []

    def step(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        ix, iy = int(self.x), int(self.y)
        if not self.history or self.history[-1] != (ix, iy):
            self.history.append((ix, iy))
        if len(self.history) > self.tail:
            self.history = self.history[-self.tail:]

    @property
    def done(self):
        return self.x > WIDTH + 4 or self.y > HEIGHT + 4


class MeteorShower(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Meteor Shower",
            "description": "Bright streaking meteors with glowing tails crossing the display",
            "category": "ambient",
        }

    def __init__(self):
        self._speed       = 5
        self._meteors     = []
        self._spawn_timer = 0.0

    def start(self) -> None:
        self._meteors     = []
        self._spawn_timer = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        speed_mul = 0.5 + self._speed * 0.10

        self._spawn_timer -= dt
        if self._spawn_timer <= 0 and len(self._meteors) < MAX_METEORS:
            self._meteors.append(_Meteor(speed_mul))
            self._spawn_timer = random.uniform(0.08, 0.50)

        for m in self._meteors:
            m.step(dt)
        self._meteors = [m for m in self._meteors if not m.done]

        for m in self._meteors:
            hist = m.history
            n    = len(hist)
            cr, cg, cb = m.color

            for idx, (tx, ty) in enumerate(hist):
                if not (0 <= tx < WIDTH and 0 <= ty < HEIGHT):
                    continue
                is_head = (idx == n - 1)
                fade    = m.bright if is_head else m.bright * (idx + 1) / n * 0.60
                r = min(255, int(cr * fade))
                g = min(255, int(cg * fade))
                b = min(255, int(cb * fade))

                if is_head:
                    for ddx, ddy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
                        nx, ny = tx + ddx, ty + ddy
                        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                            hf = 1.0 if (ddx == 0 and ddy == 0) else 0.45
                            cur = frame[ny, nx]
                            frame[ny, nx] = (max(cur[0], int(r*hf)), max(cur[1], int(g*hf)), max(cur[2], int(b*hf)))
                else:
                    cur = frame[ty, tx]
                    frame[ty, tx] = (max(cur[0], r), max(cur[1], g), max(cur[2], b))

        return frame

    def get_settings(self) -> list[dict]:
        return [{"key": "speed", "label": "Speed", "type": "range",
                 "min": 1, "max": 10, "step": 1, "value": self._speed}]

    def apply_setting(self, key: str, value) -> None:
        if key == "speed":
            self._speed = max(1, min(10, int(value)))
