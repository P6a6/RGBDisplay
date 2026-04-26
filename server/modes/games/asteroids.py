import math
import random

import numpy as np
from base_mode import BaseMode

W = 64
H = 64

# ── Palette ───────────────────────────────────────────────────────────────────
C_SHIP      = (220, 220, 255)
C_THRUST    = (255, 120,  20)
C_BULLET    = (255, 255, 100)
C_AST_L     = (180, 180, 180)   # large
C_AST_M     = (200, 160, 100)   # medium
C_AST_S     = (220, 100,  80)   # small
C_SCORE     = (180, 180, 180)
C_LIFE      = (100, 180, 255)
C_TITLE     = (255, 255, 255)
C_SUBTITLE  = (160, 160, 200)
C_GAMEOVER  = (255,  60,  60)
C_FLASH     = (255, 255, 255)

# ── Asteroid sizes ────────────────────────────────────────────────────────────
AST_RADIUS  = [5, 3, 2]          # large / medium / small
AST_SPEED   = [0.22, 0.38, 0.58] # base speed — tuned for 64px screen at 30fps
AST_SCORE   = [20, 50, 100]
AST_VERTS   = [11, 8, 6]

# ── Difficulty: speed multiplier + starting asteroid count ────────────────────
#   Easy:   large ~0.14 px/tick  (crosses screen in ~7 s), 3 rocks to start
#   Normal: large ~0.22 px/tick  (crosses screen in ~4.5 s), 4 rocks
#   Hard:   large ~0.33 px/tick  (crosses screen in ~3 s), 5 rocks
DIFF_SPEED  = [0.65, 1.0, 1.5]
DIFF_COUNT  = [3, 4, 5]          # starting asteroid count per difficulty

# ── Physics constants ─────────────────────────────────────────────────────────
ROTATE_SPEED = 9.0
THRUST_ACC   = 0.20             # was 0.35 — gentler acceleration
MAX_SPEED    = 3.0              # was 5.5 — lower top speed
DRAG         = 0.978            # was 0.985 — more friction, easier to control
BULLET_SPEED = 7.0
BULLET_LIFE  = 0.55
FIRE_COOLDOWN = 0.18
INVINCIBLE_T  = 2.5
RESPAWN_DELAY = 1.2
START_LIVES   = 3
EXTRA_LIFE_PT = 10000
INIT_ASTEROIDS = 4              # overridden by DIFF_COUNT in _spawn_wave

# ── 3×5 mini-font ─────────────────────────────────────────────────────────────
_FONT: dict[str, list[int]] = {
    ' ': [0, 0, 0],
    'A': [15, 20, 15], 'B': [31, 21, 10], 'C': [14, 17, 17],
    'D': [31, 17, 14], 'E': [31, 21, 17], 'F': [31, 20, 16],
    'G': [14, 21, 23], 'H': [31,  4, 31], 'I': [17, 31, 17],
    'J': [ 2, 17, 30], 'K': [31,  4, 27], 'L': [31,  1,  1],
    'M': [31, 24,  4, 24, 31],             'N': [31,  8,  4, 31],
    'O': [14, 17, 14], 'P': [31, 20, 24], 'Q': [14, 17, 15],
    'R': [31, 20, 11], 'S': [ 9, 21, 18], 'T': [16, 31, 16],
    'U': [30,  1, 30], 'V': [28,  3, 28], 'W': [31,  2,  4,  2, 31],
    'X': [27,  4, 27], 'Y': [24,  7, 24], 'Z': [19, 21,  9],
    '0': [14, 17, 14], '1': [ 9, 31,  1], '2': [23, 21, 29],
    '3': [21, 21, 31], '4': [28,  4, 31], '5': [29, 21, 23],
    '6': [31, 21,  7], '7': [16, 19, 28], '8': [10, 21, 10],
    '9': [12, 21, 14], '-': [ 4,  4,  4], '!': [ 0, 23,  0],
    ':': [ 0, 10,  0],
}


def _text_width(text: str) -> int:
    return sum(len(_FONT.get(c.upper(), _FONT[' '])) + 1 for c in text) - 1


def _draw_text(frame: np.ndarray, x: int, y: int, text: str, color,
               scale: int = 1) -> None:
    cx = x
    for ch in text:
        cols = _FONT.get(ch.upper(), _FONT[' '])
        for ci, bits in enumerate(cols):
            for ri in range(5):
                if bits & (1 << (4 - ri)):
                    for dy in range(scale):
                        for dx in range(scale):
                            px = cx + ci * scale + dx
                            py = y  + ri * scale + dy
                            if 0 <= px < W and 0 <= py < H:
                                frame[py, px] = color
        cx += (len(cols) + 1) * scale


def _draw_centered(frame: np.ndarray, y: int, text: str, color,
                   scale: int = 1) -> None:
    w = _text_width(text) * scale
    _draw_text(frame, (W - w) // 2, y, text, color, scale)


# ── Bresenham line ─────────────────────────────────────────────────────────────
def _line(frame: np.ndarray, x0: int, y0: int, x1: int, y1: int,
          color, wrap: bool = True) -> None:
    dx = abs(x1 - x0); dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        px = x % W if wrap else x
        py = y % H if wrap else y
        if 0 <= px < W and 0 <= py < H:
            frame[py, px] = color
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy; x += sx
        if e2 < dx:
            err += dx; y += sy


def _poly(frame: np.ndarray, verts, color, wrap: bool = True) -> None:
    n = len(verts)
    for i in range(n):
        x0, y0 = int(round(verts[i][0])),          int(round(verts[i][1]))
        x1, y1 = int(round(verts[(i+1) % n][0])), int(round(verts[(i+1) % n][1]))
        _line(frame, x0, y0, x1, y1, color, wrap)


# ── Asteroid shape generation ─────────────────────────────────────────────────
def _make_shape(gen: int, seed: int) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    n   = AST_VERTS[gen]
    r   = AST_RADIUS[gen]
    pts = []
    for i in range(n):
        angle  = 2 * math.pi * i / n + rng.uniform(-0.25, 0.25)
        radius = r * rng.uniform(0.65, 1.25)
        pts.append((math.cos(angle) * radius, math.sin(angle) * radius))
    return pts


# ── Entities ──────────────────────────────────────────────────────────────────
class _Asteroid:
    __slots__ = ('x', 'y', 'vx', 'vy', 'gen', 'shape', 'angle', 'spin')

    def __init__(self, x, y, vx, vy, gen, seed=None):
        self.x  = float(x); self.y = float(y)
        self.vx = float(vx); self.vy = float(vy)
        self.gen   = gen
        self.shape = _make_shape(gen, seed if seed is not None else random.randint(0, 99999))
        self.angle = random.uniform(0, 360)
        self.spin  = random.uniform(-1.5, 1.5)   # degrees per tick

    def tick(self) -> None:
        self.x = (self.x + self.vx) % W
        self.y = (self.y + self.vy) % H
        self.angle = (self.angle + self.spin) % 360

    def verts(self) -> list[tuple[float, float]]:
        a = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        return [(self.x + ca * px - sa * py,
                 self.y + sa * px + ca * py)
                for px, py in self.shape]

    def radius(self) -> float:
        return AST_RADIUS[self.gen]

    def color(self):
        return (C_AST_L, C_AST_M, C_AST_S)[self.gen]


class _Bullet:
    __slots__ = ('x', 'y', 'vx', 'vy', 'life')

    def __init__(self, x, y, angle_deg):
        a = math.radians(angle_deg)
        self.x  = float(x); self.y = float(y)
        self.vx = math.sin(a) * BULLET_SPEED
        self.vy = -math.cos(a) * BULLET_SPEED
        self.life = BULLET_LIFE

    def tick(self, dt: float) -> bool:
        self.x = (self.x + self.vx) % W
        self.y = (self.y + self.vy) % H
        self.life -= dt
        return self.life > 0


class _Ship:
    __slots__ = ('x', 'y', 'vx', 'vy', 'angle', 'dead', 'invincible',
                 'respawn_timer', 'thrust_on', '_flash')

    def __init__(self):
        self.x  = W / 2.0; self.y = H / 2.0
        self.vx = 0.0;      self.vy = 0.0
        self.angle        = 0.0
        self.dead         = False
        self.invincible   = INVINCIBLE_T
        self.respawn_timer = 0.0
        self.thrust_on    = False
        self._flash       = 0.0

    def tick(self, dt: float, rotate: int, thrusting: bool) -> None:
        self.angle = (self.angle + rotate * ROTATE_SPEED) % 360
        if thrusting:
            a = math.radians(self.angle)
            self.vx += math.sin(a) * THRUST_ACC
            self.vy -= math.cos(a) * THRUST_ACC
            speed = math.hypot(self.vx, self.vy)
            if speed > MAX_SPEED:
                self.vx = self.vx / speed * MAX_SPEED
                self.vy = self.vy / speed * MAX_SPEED
        self.vx *= DRAG
        self.vy *= DRAG
        self.x = (self.x + self.vx) % W
        self.y = (self.y + self.vy) % H
        if self.invincible > 0:
            self.invincible -= dt
            self._flash = (self._flash + dt * 8) % (2 * math.pi)

    def nose(self) -> tuple[float, float]:
        a = math.radians(self.angle)
        return (self.x + math.sin(a) * 4, self.y - math.cos(a) * 4)

    def verts(self) -> list[tuple[float, float]]:
        a  = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        pts = [(0, -4), (-2.5, 3), (0, 1.5), (2.5, 3)]  # nose, L-base, tail-notch, R-base
        return [(self.x + ca * px - sa * py,
                 self.y + sa * px + ca * py)
                for px, py in pts]

    def visible(self) -> bool:
        if self.invincible > 0:
            return math.sin(self._flash) > 0
        return True


# ── Particle (thrust + explosion) ────────────────────────────────────────────
class _Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'life', 'max_life', 'color')

    def __init__(self, x, y, vx, vy, life, color):
        self.x = float(x); self.y = float(y)
        self.vx = float(vx); self.vy = float(vy)
        self.life = self.max_life = float(life)
        self.color = color

    def tick(self, dt: float) -> bool:
        self.x = (self.x + self.vx) % W
        self.y = (self.y + self.vy) % H
        self.life -= dt
        return self.life > 0

    def draw(self, frame: np.ndarray) -> None:
        frac = max(0.0, self.life / self.max_life)
        r = int(self.color[0] * frac)
        g = int(self.color[1] * frac)
        b = int(self.color[2] * frac)
        px, py = int(self.x) % W, int(self.y) % H
        frame[py, px] = (r, g, b)


# ── Main mode ─────────────────────────────────────────────────────────────────
class Asteroids(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name":        "Asteroids",
            "description": "Classic 1979 shooter. Shoot rocks, don't get hit.",
            "category":    "games",
        }

    def __init__(self):
        self._difficulty = 1       # 0=Easy  1=Normal  2=Hard
        self._lives    = START_LIVES
        self._score    = 0
        self._hi_score = 0
        self._state    = "title"   # title | playing | dead_wait | game_over
        self._ship: _Ship | None = None
        self._asteroids: list[_Asteroid] = []
        self._bullets:   list[_Bullet]   = []
        self._particles: list[_Particle] = []
        self._wave      = 0
        self._fire_cd   = 0.0
        self._rotate    = 0     # -1 / 0 / +1
        self._thrusting = False
        self._fire_req  = False
        self._dead_t    = 0.0
        self._flash_t   = 0.0
        self._extra_life_threshold = EXTRA_LIFE_PT
        self._title_t   = 0.0

    # ── BaseMode interface ────────────────────────────────────────────────────
    def start(self) -> None:
        self._state = "title"
        self._title_t = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        if self._state == "title":
            self._tick_title(dt, frame)
        elif self._state == "playing":
            self._tick_game(dt, frame)
        elif self._state == "dead_wait":
            self._tick_dead_wait(dt, frame)
        elif self._state == "game_over":
            self._tick_game_over(dt, frame)
        return frame

    def handle_input(self, player: int, action: str) -> None:
        if player != 0:
            return
        if self._state == "title":
            if action == "start":
                self._new_game()
            return
        if self._state == "game_over":
            if action == "start":
                self._state = "title"
            return
        # playing / dead_wait
        if action == "left":
            self._rotate = -1
        elif action == "right":
            self._rotate = 1
        elif action == "up":
            self._thrusting = True
        elif action == "a" or action == "b" or action == "x" or action == "y":
            self._fire_req = True
        # releasing direction — handled by absence of repeated input from the
        # d-pad auto-repeat; we reset rotate/thrust each tick via _tick_game

    def is_over(self) -> bool:
        return self._state == "game_over"

    def get_settings(self) -> list[dict]:
        return [{
            "key":     "difficulty",
            "label":   "Difficulty",
            "type":    "select",
            "options": [
                {"value": 0, "label": "Easy"},
                {"value": 1, "label": "Normal"},
                {"value": 2, "label": "Hard"},
            ],
            "value": self._difficulty,
        }]

    def apply_setting(self, key: str, value) -> None:
        if key == "difficulty":
            self._difficulty = max(0, min(2, int(value)))

    # ── Game init ─────────────────────────────────────────────────────────────
    def _new_game(self) -> None:
        self._lives    = START_LIVES
        self._score    = 0
        self._wave     = 0
        self._extra_life_threshold = EXTRA_LIFE_PT
        self._bullets  = []
        self._particles = []
        self._ship     = _Ship()
        self._state    = "playing"
        self._spawn_wave(first=True)

    def _spawn_wave(self, first: bool = False) -> None:
        self._wave += 1
        count = DIFF_COUNT[self._difficulty] + (self._wave - 1)
        self._asteroids = []
        spd_mul = DIFF_SPEED[self._difficulty]
        for _ in range(count):
            # Spawn away from ship centre
            while True:
                x = random.uniform(0, W)
                y = random.uniform(0, H)
                if math.hypot(x - W/2, y - H/2) > 18:
                    break
            speed = AST_SPEED[0] * spd_mul * random.uniform(0.8, 1.2)
            ang   = random.uniform(0, 2 * math.pi)
            self._asteroids.append(_Asteroid(x, y, math.cos(ang)*speed,
                                             math.sin(ang)*speed, gen=0))

    def _respawn_ship(self) -> None:
        self._ship = _Ship()
        self._bullets = []
        self._state   = "playing"

    # ── Tick states ───────────────────────────────────────────────────────────
    def _tick_title(self, dt: float, frame: np.ndarray) -> None:
        self._title_t += dt
        # Slowly drift some asteroids in background
        if not self._asteroids:
            for _ in range(5):
                ang = random.uniform(0, 2*math.pi)
                s   = random.uniform(0.3, 0.7)
                self._asteroids.append(
                    _Asteroid(random.uniform(0,W), random.uniform(0,H),
                              math.cos(ang)*s, math.sin(ang)*s, gen=random.randint(0,2)))
        for a in self._asteroids:
            a.tick()
        for a in self._asteroids:
            _poly(frame, a.verts(), a.color())
        # Title: "ASTEROIDS" at scale=1 fits (35px wide). Pad with star decorations.
        ty = 10
        _draw_centered(frame, ty,      "* ASTEROIDS *", C_TITLE)
        _draw_centered(frame, ty + 8,  "- - - - - - -", C_SUBTITLE)
        diff_label = ("EASY", "NORMAL", "HARD")[self._difficulty]
        _draw_centered(frame, 30, diff_label, (100, 220, 120) if self._difficulty == 0
                       else (220, 220, 80) if self._difficulty == 1 else (255, 80, 80))
        _draw_centered(frame, 40, "PRESS START", C_SUBTITLE)
        if self._hi_score > 0:
            _draw_centered(frame, 52, f"HI {self._hi_score}", C_SCORE)

    def _tick_game(self, dt: float, frame: np.ndarray) -> None:
        ship = self._ship

        # ── D-pad auto-repeat: reset momentary controls each tick ─────────────
        rotate_this    = self._rotate
        thrusting_this = self._thrusting
        self._rotate    = 0
        self._thrusting = False

        # ── Ship movement ──────────────────────────────────────────────────────
        if ship:
            ship.tick(dt, rotate_this, thrusting_this)

            # Thrust particles
            if thrusting_this:
                a    = math.radians(ship.angle + 180)
                base = (ship.x + math.sin(a)*4, ship.y - math.cos(a)*4)
                for _ in range(2):
                    spread = random.uniform(-0.4, 0.4)
                    speed  = random.uniform(1.5, 3.5)
                    self._particles.append(_Particle(
                        base[0], base[1],
                        math.sin(a + spread) * speed,
                        -math.cos(a + spread) * speed,
                        life=random.uniform(0.12, 0.28),
                        color=(255, random.randint(80, 160), 20)))

        # ── Fire ──────────────────────────────────────────────────────────────
        self._fire_cd = max(0.0, self._fire_cd - dt)
        if self._fire_req and self._fire_cd == 0.0 and ship:
            nx, ny = ship.nose()
            self._bullets.append(_Bullet(nx, ny, ship.angle))
            self._fire_cd = FIRE_COOLDOWN
        self._fire_req = False

        # ── Update bullets ────────────────────────────────────────────────────
        self._bullets = [b for b in self._bullets if b.tick(dt)]

        # ── Update asteroids ──────────────────────────────────────────────────
        for a in self._asteroids:
            a.tick()

        # ── Update particles ──────────────────────────────────────────────────
        self._particles = [p for p in self._particles if p.tick(dt)]

        # ── Collisions: bullets vs asteroids ─────────────────────────────────
        new_asts  = []
        dead_asts = set()
        dead_buls = set()
        for bi, b in enumerate(self._bullets):
            for ai, a in enumerate(self._asteroids):
                if ai in dead_asts:
                    continue
                if math.hypot(b.x - a.x, b.y - a.y) < a.radius() * 0.9:
                    dead_asts.add(ai)
                    dead_buls.add(bi)
                    self._score += AST_SCORE[a.gen]
                    # Extra life milestone
                    if self._score >= self._extra_life_threshold:
                        self._lives += 1
                        self._extra_life_threshold += EXTRA_LIFE_PT
                    # Explosion particles
                    self._explode(a.x, a.y, a.gen)
                    # Split
                    if a.gen < 2:
                        spd_mul = DIFF_SPEED[self._difficulty]
                        base_spd = AST_SPEED[a.gen + 1] * spd_mul
                        for sign in (-1, 1):
                            ang = math.atan2(a.vy, a.vx) + sign * math.pi * 0.4
                            nvx = math.cos(ang) * base_spd * random.uniform(0.85, 1.15)
                            nvy = math.sin(ang) * base_spd * random.uniform(0.85, 1.15)
                            new_asts.append(_Asteroid(
                                a.x, a.y, nvx, nvy, gen=a.gen + 1))
                    break

        self._asteroids = [a for i, a in enumerate(self._asteroids) if i not in dead_asts] + new_asts
        self._bullets   = [b for i, b in enumerate(self._bullets)   if i not in dead_buls]

        # ── Collision: ship vs asteroids ──────────────────────────────────────
        if ship and ship.invincible <= 0:
            for a in self._asteroids:
                if math.hypot(ship.x - a.x, ship.y - a.y) < a.radius() + 2:
                    self._kill_ship(ship)
                    break

        # ── Wave clear ────────────────────────────────────────────────────────
        if not self._asteroids:
            self._spawn_wave()

        # ── Draw ──────────────────────────────────────────────────────────────
        for p in self._particles:
            p.draw(frame)

        for a in self._asteroids:
            _poly(frame, a.verts(), a.color())

        for b in self._bullets:
            bx, by = int(b.x) % W, int(b.y) % H
            frame[by, bx] = C_BULLET
            # Small glow dot around bullet
            for ox, oy in ((-1,0),(1,0),(0,-1),(0,1)):
                nx2, ny2 = (bx+ox)%W, (by+oy)%H
                if frame[ny2, nx2].sum() < 50:
                    frame[ny2, nx2] = (120, 120, 50)

        if ship and ship.visible():
            v = ship.verts()
            # Draw ship outline: nose→L-base, nose→R-base, L-base→notch→R-base
            _line(frame, int(v[0][0]), int(v[0][1]), int(v[1][0]), int(v[1][1]), C_SHIP)
            _line(frame, int(v[0][0]), int(v[0][1]), int(v[3][0]), int(v[3][1]), C_SHIP)
            _line(frame, int(v[1][0]), int(v[1][1]), int(v[2][0]), int(v[2][1]), C_SHIP)
            _line(frame, int(v[2][0]), int(v[2][1]), int(v[3][0]), int(v[3][1]), C_SHIP)

        # HUD
        self._draw_hud(frame)

    def _tick_dead_wait(self, dt: float, frame: np.ndarray) -> None:
        # Asteroids keep moving
        for a in self._asteroids:
            a.tick()
        self._particles = [p for p in self._particles if p.tick(dt)]
        for p in self._particles:
            p.draw(frame)
        for a in self._asteroids:
            _poly(frame, a.verts(), a.color())
        self._draw_hud(frame)

        self._dead_t -= dt
        if self._dead_t <= 0:
            if self._lives > 0:
                self._respawn_ship()
            else:
                if self._score > self._hi_score:
                    self._hi_score = self._score
                self._state = "game_over"

    def _tick_game_over(self, dt: float, frame: np.ndarray) -> None:
        _draw_centered(frame, 18, "GAME",  C_GAMEOVER, scale=2)
        _draw_centered(frame, 32, "OVER",  C_GAMEOVER, scale=2)
        sc = str(self._score)
        _draw_centered(frame, 48, sc,      C_SCORE)
        _draw_centered(frame, 56, "START", C_SUBTITLE)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _kill_ship(self, ship: _Ship) -> None:
        self._explode(ship.x, ship.y, gen=-1)
        self._lives -= 1
        self._ship   = None
        self._dead_t = RESPAWN_DELAY
        self._state  = "dead_wait"

    def _explode(self, x: float, y: float, gen: int) -> None:
        count = 18 if gen < 0 else (12, 8, 5)[gen]
        col   = C_SHIP if gen < 0 else (C_AST_L, C_AST_M, C_AST_S)[gen]
        for _ in range(count):
            ang   = random.uniform(0, 2*math.pi)
            speed = random.uniform(0.5, 2.5 if gen < 0 else 1.8)
            life  = random.uniform(0.3, 0.8 if gen < 0 else 0.5)
            self._particles.append(_Particle(
                x, y, math.cos(ang)*speed, math.sin(ang)*speed, life, col))

    def _draw_hud(self, frame: np.ndarray) -> None:
        # Score — top-left
        _draw_text(frame, 1, 1, str(self._score), C_SCORE)
        # Lives — top-right as small triangles
        for i in range(self._lives):
            lx = W - 4 - i * 5
            frame[1, lx]   = C_LIFE
            frame[2, lx-1] = C_LIFE
            frame[2, lx]   = C_LIFE
            frame[2, lx+1] = C_LIFE
