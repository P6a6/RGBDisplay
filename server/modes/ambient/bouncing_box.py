import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64

SIZES = {"small": 6, "medium": 12, "large": 20}
SPEED = 32.0

_FONT = {
    'P': (0x7F, 0x09, 0x09, 0x09, 0x06),
    'A': (0x7E, 0x11, 0x11, 0x11, 0x7E),
    'R': (0x7F, 0x09, 0x19, 0x29, 0x46),
    'S': (0x46, 0x49, 0x49, 0x49, 0x31),
}

# Neon colour options — cycle through these each full erase→restore pass
_NEON = [
    (0,   255,  80),   # green
    (0,   220, 255),   # cyan
    (255, 220,   0),   # yellow
    (200,   0, 255),   # purple
    (255,  80, 200),   # pink
    (0,   160, 255),   # blue
    (255, 120,   0),   # orange
]

def _build_text_pixels(text: str) -> list[tuple[int, int]]:
    raw, cx = [], 0
    for ch in text:
        bm = _FONT.get(ch.upper())
        if bm is None:
            cx += 6; continue
        for col, byte in enumerate(bm):
            for row in range(7):
                if byte & (1 << row):
                    raw.append((cx + col, row))
        cx += 6
    tw = cx - 1
    x0 = (WIDTH  - tw) // 2
    y0 = (HEIGHT - 7)  // 2
    return [(x + x0, y + y0) for x, y in raw]

_TEXT_PIXELS = _build_text_pixels("PARSA")
_N_PIXELS    = len(_TEXT_PIXELS)


class BouncingBox(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Bouncing Box",
            "description": "Box erases PARSA pixel by pixel then restores it — colour changes each cycle",
            "category": "ambient",
        }

    def __init__(self):
        self._size_key   = "medium"
        self._trail: list[tuple[int, int, float]] = []
        self._color_idx  = 0
        # visibility[i] = True → pixel i is currently shown
        self._visible    = [True] * _N_PIXELS
        self._mode       = 'erase'   # 'erase' | 'restore'
        self._flicker_t  = 0.0
        self._reset()

    def _reset(self):
        self._x  = float(WIDTH  // 2)
        self._y  = float(HEIGHT // 2)
        self._vx = SPEED * 0.7
        self._vy = SPEED * 0.9
        self._trail = []

    def _next_color(self):
        self._color_idx = (self._color_idx + 1) % len(_NEON)

    def start(self) -> None:
        self._reset()
        self._visible  = [True] * _N_PIXELS
        self._mode     = 'erase'

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        self._flicker_t += dt
        size = SIZES[self._size_key]
        half = size // 2

        # ── Move box ──────────────────────────────────────────────────────────
        self._trail.append((int(self._x), int(self._y), 0.0))
        self._trail = [(tx, ty, a + dt * 5.0)
                       for tx, ty, a in self._trail if a + dt * 5.0 < 1.0][-10:]

        self._x += self._vx * dt
        self._y += self._vy * dt

        if self._x - half < 0:
            self._x = float(half);            self._vx =  abs(self._vx)
        elif self._x + half >= WIDTH:
            self._x = float(WIDTH - 1 - half); self._vx = -abs(self._vx)
        if self._y - half < 0:
            self._y = float(half);             self._vy =  abs(self._vy)
        elif self._y + half >= HEIGHT:
            self._y = float(HEIGHT - 1 - half);self._vy = -abs(self._vy)

        bx, by = int(self._x), int(self._y)
        bx0, bx1 = bx - half, bx + half
        by0, by1 = by - half, by + half

        # ── Erase / restore pixels the box passes over ────────────────────────
        changed = False
        for i, (px, py) in enumerate(_TEXT_PIXELS):
            if bx0 <= px <= bx1 and by0 <= py <= by1:
                if self._mode == 'erase' and self._visible[i]:
                    self._visible[i] = False
                    changed = True
                elif self._mode == 'restore' and not self._visible[i]:
                    self._visible[i] = True
                    changed = True

        # ── Mode transitions ──────────────────────────────────────────────────
        if self._mode == 'erase' and not any(self._visible):
            self._mode = 'restore'
            self._next_color()
        elif self._mode == 'restore' and all(self._visible):
            self._mode = 'erase'

        # ── Draw ──────────────────────────────────────────────────────────────
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        # Neon text with subtle flicker
        cr, cg, cb = _NEON[self._color_idx]
        flicker = 0.80 + 0.20 * abs(((self._flicker_t * 7.3) % 1.0) * 2 - 1)
        # Occasional stronger flicker spike
        if random.random() < 0.04:
            flicker *= random.uniform(0.3, 0.7)
        for i, (px, py) in enumerate(_TEXT_PIXELS):
            if self._visible[i]:
                f = flicker * random.uniform(0.88, 1.0)
                frame[py, px] = (int(cr * f), int(cg * f), int(cb * f))

        # Trail (fading ghost boxes)
        for tx, ty, age in self._trail:
            alpha = max(0.0, 1.0 - age) * 0.20
            self._draw_box(frame, tx, ty, size, alpha)

        # Current box outline
        self._draw_box(frame, bx, by, size, 1.0)

        return frame

    def _draw_box(self, frame: np.ndarray, cx: int, cy: int, size: int, brightness: float):
        half  = size // 2
        color = np.array([int(60 * brightness), int(255 * brightness), int(60 * brightness)], dtype=np.uint8)
        x0 = max(0, cx - half); x1 = min(WIDTH  - 1, cx + half)
        y0 = max(0, cy - half); y1 = min(HEIGHT - 1, cy + half)
        if y0 < HEIGHT: frame[y0, x0:x1+1] = np.maximum(frame[y0, x0:x1+1], color)
        if y1 < HEIGHT: frame[y1, x0:x1+1] = np.maximum(frame[y1, x0:x1+1], color)
        if x0 < WIDTH:  frame[y0:y1+1, x0] = np.maximum(frame[y0:y1+1, x0], color)
        if x1 < WIDTH:  frame[y0:y1+1, x1] = np.maximum(frame[y0:y1+1, x1], color)

    def get_settings(self) -> list[dict]:
        return [{"key": "size", "label": "Box Size", "type": "select",
                 "value": self._size_key,
                 "options": [{"value": "small",  "label": "Small"},
                              {"value": "medium", "label": "Medium"},
                              {"value": "large",  "label": "Large"}]}]

    def apply_setting(self, key: str, value) -> None:
        if key == "size" and value in SIZES:
            self._size_key = value
            self._reset()
