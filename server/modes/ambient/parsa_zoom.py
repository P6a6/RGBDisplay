import math
import random
import numpy as np
from base_mode import BaseMode

WIDTH  = 64
HEIGHT = 64
CX     = WIDTH  / 2.0
CY     = HEIGHT / 2.0

# ── Font ──────────────────────────────────────────────────────────────────────
_FONT = {
    'P': (0x7F, 0x09, 0x09, 0x09, 0x06),
    'A': (0x7E, 0x11, 0x11, 0x11, 0x7E),
    'R': (0x7F, 0x09, 0x19, 0x29, 0x46),
    'S': (0x46, 0x49, 0x49, 0x49, 0x31),
}
_TEXT   = "PARSA"
_CHAR_W = 6
_CHAR_H = 7

def _build_pixels(text):
    raw, ox = [], 0
    for ch in text:
        bm = _FONT.get(ch.upper(), (0,)*5)
        for col, byte in enumerate(bm):
            for row in range(_CHAR_H):
                if byte & (1 << row):
                    raw.append((ox + col, row))
        ox += _CHAR_W
    cx = (ox - 1) / 2.0
    cy = (_CHAR_H - 1) / 2.0
    return [(x - cx, y - cy) for x, y in raw]

_PIXELS = _build_pixels(_TEXT)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _hsv(h, s, v):
    h6 = h * 6.0
    i  = int(h6) % 6
    f  = h6 - math.floor(h6)
    p  = v*(1-s); q = v*(1-s*f); t = v*(1-s*(1-f))
    r, g, b = [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i]
    return (int(r*255), int(g*255), int(b*255))


# ── Starfield ─────────────────────────────────────────────────────────────────
# Identical rendering to the Starfield mode: pixel trails, proximity brightness,
# bluish-white colour, no squares. Slower speed than Starfield for calmer feel.
_N_STARS   = 100
_TRAIL_LEN = 6
_WARP      = 0.10   # z consumed per second (Starfield uses ~0.3-0.4; this is slower)

class _Star:
    def __init__(self, spread_z=True):
        self.x     = random.uniform(-1.0, 1.0)
        self.y     = random.uniform(-1.0, 1.0)
        self.z     = random.uniform(0.4, 1.0) if spread_z else 1.0
        self.trail = []

    def reset(self):
        self.x     = random.uniform(-1.0, 1.0)
        self.y     = random.uniform(-1.0, 1.0)
        self.z     = 1.0
        self.trail = []

    @staticmethod
    def _color(z, brightness):
        t = max(0.0, min(1.0, 1.0 - z))
        r = int((180 + 75*t) * brightness)
        g = int((190 + 65*t) * brightness)
        b = int((255 - 55*t) * brightness)
        return (min(255,r), min(255,g), min(255,b))

    def advance(self, dt):
        self.z -= _WARP * dt
        if self.z <= 0.015:
            self.reset(); return
        sx = int(self.x / self.z * CX + CX)
        sy = int(self.y / self.z * CY + CY)
        if not (0 <= sx < WIDTH and 0 <= sy < HEIGHT):
            self.reset(); return
        self.trail.append((sx, sy))
        if len(self.trail) > _TRAIL_LEN:
            self.trail = self.trail[-_TRAIL_LEN:]

    def draw(self, frame):
        if not self.trail:
            return
        proximity  = 1.0 - self.z
        brightness = min(1.0, proximity ** 1.1 + 0.05)
        n = len(self.trail)
        for idx, (tx, ty) in enumerate(self.trail):
            is_head = (idx == n - 1)
            tb = brightness if is_head else brightness * (idx + 1) / n * 0.55
            r, g, b = self._color(self.z, tb)
            # Head grows when very close — same logic as Starfield
            if is_head and self.z < 0.12:
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        nx, ny = tx+dx, ty+dy
                        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                            cur = frame[ny, nx]
                            frame[ny, nx] = (max(cur[0],r), max(cur[1],g), max(cur[2],b))
            elif is_head and self.z < 0.28:
                for ddx, ddy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = tx+ddx, ty+ddy
                    if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                        cur = frame[ny, nx]
                        frame[ny, nx] = (max(cur[0],r), max(cur[1],g), max(cur[2],b))
            else:
                if 0 <= tx < WIDTH and 0 <= ty < HEIGHT:
                    cur = frame[ty, tx]
                    frame[ty, tx] = (max(cur[0],r), max(cur[1],g), max(cur[2],b))


# ── Text zoom pass ────────────────────────────────────────────────────────────
class _Zoom:
    def __init__(self):
        self.scale = 0.10
        # Exponential growth rate: scale *= (1 + rate*dt) each frame.
        # Small scale → slow growth. Large scale → fast growth.
        # rate≈0.85 → 6-8 second journey until all pixels leave the frame.
        self.rate  = random.uniform(0.80, 0.95)
        self.done  = False
        h = random.random()
        self.color    = _hsv(h, 0.75, 1.0)
        self.glow_col = _hsv(h, 0.35, 1.0)

    def advance(self, dt):
        self.scale *= (1.0 + self.rate * dt)
        # Done only when every single pixel block is fully outside the frame
        block = max(1, int(self.scale * 0.55))
        half  = block // 2
        all_off = True
        for px, py in _PIXELS:
            sx = int(CX + px * self.scale)
            sy = int(CY + py * self.scale)
            # Pixel still on screen if any part of its block overlaps the frame
            if (sx + half >= 0 and sx - half < WIDTH and
                    sy + half >= 0 and sy - half < HEIGHT):
                all_off = False
                break
        if all_off:
            self.done = True
        return self.done

    def draw(self, frame):
        scale = self.scale
        cr, cg, cb = self.color
        gr, gg, gb = self.glow_col
        block = max(1, int(scale * 0.55))

        for px, py in _PIXELS:
            sx = CX + px * scale
            sy = CY + py * scale
            ix, iy = int(sx), int(sy)

            # Fade as pixels approach/cross the edge
            edge_dist = min(ix, WIDTH - 1 - ix, iy, HEIGHT - 1 - iy)
            fade = min(1.0, max(0.0, edge_dist / 5.0))
            if fade == 0:
                continue

            r = int(cr * fade); g = int(cg * fade); b = int(cb * fade)

            half = block // 2
            for dy in range(-half, half + 1):
                for dx in range(-half, half + 1):
                    nx, ny = ix + dx, iy + dy
                    if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                        cur = frame[ny, nx]
                        frame[ny, nx] = (max(cur[0], r), max(cur[1], g), max(cur[2], b))

            # Glow fringe
            gf = fade * 0.30
            gr_v = int(gr * gf); gg_v = int(gg * gf); gb_v = int(gb * gf)
            if gr_v or gg_v or gb_v:
                for dy in range(-half - 1, half + 2):
                    for dx in range(-half - 1, half + 2):
                        if abs(dx) <= half and abs(dy) <= half:
                            continue
                        nx, ny = ix + dx, iy + dy
                        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                            cur = frame[ny, nx]
                            frame[ny, nx] = (max(cur[0], gr_v), max(cur[1], gg_v), max(cur[2], gb_v))


# ── Mode ──────────────────────────────────────────────────────────────────────
class ParsaZoom(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Parsa",
            "description": "PARSA rushes toward the camera through a starfield and blows past it",
            "category": "ambient",
        }

    def __init__(self):
        self._stars = [_Star(spread_z=True) for _ in range(_N_STARS)]
        self._zoom: _Zoom | None = None
        self._pause = 0.8

    def start(self) -> None:
        for s in self._stars:
            s._spawn(spread_z=True)
        self._zoom  = None
        self._pause = random.uniform(0.5, 1.2)

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        # Stars always run — even during pause between text passes
        for star in self._stars:
            star.advance(dt)
            star.draw(frame)

        # Text zoom
        if self._zoom is None:
            self._pause -= dt
            if self._pause <= 0:
                self._zoom = _Zoom()
        else:
            self._zoom.draw(frame)
            if self._zoom.advance(dt):
                self._zoom  = None
                # Pause after text blows past: stars keep flying, text is gone
                self._pause = random.uniform(2.5, 5.0)

        return frame

    def get_settings(self) -> list[dict]:
        return []
