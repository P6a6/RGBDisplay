"""
Road Fighter — scrolling top-down car dodge inspired by the 1984 Konami arcade game.

Controls
--------
  D-pad left / right : steer
  Gyro (tilt phone)  : steer when Control = Gyro or Both
  Up / down          : speed boost / brake
  Select             : pause / resume
"""
import math
import random

import numpy as np
from base_mode import BaseMode

W = 64
H = 64

# ── Road geometry ─────────────────────────────────────────────────────────────
ROAD_L  = 13
ROAD_R  = 50
ROAD_W  = ROAD_R - ROAD_L + 1
CENTER  = (ROAD_L + ROAD_R) // 2   # 31

PLAYER_W   = 4
PLAYER_H   = 7
PLAYER_Y   = 54
PLAYER_MIN_X = ROAD_L + PLAYER_W // 2 + 1
PLAYER_MAX_X = ROAD_R - PLAYER_W // 2 - 1

# ── Colours ───────────────────────────────────────────────────────────────────
C_GRASS_D  = ( 14,  62,  14)
C_GRASS_L  = ( 22,  88,  22)
C_SHOULDER = ( 50,  46,  32)
C_ROAD     = ( 44,  44,  47)
C_LINE     = (170, 170, 170)
C_DASH     = (180, 155,  30)
C_PLAYER   = ( 35, 100, 220)
C_PLAYER_D = ( 16,  48, 110)
C_PLAYER_W = (140, 190, 220)
C_FUEL     = ( 45, 180,  60)
C_SCORE    = (180, 180, 180)
C_TITLE    = (240, 240, 240)
C_SUBTITLE = (130, 130, 170)
C_GAMEOVER = (220,  48,  48)
C_SPEED_HI = (220, 170,  30)
C_PAUSE    = (120, 200, 255)

TRAFFIC_PALETTES = [
    [(190,  40,  40), (220, 140, 140), (110,  16,  16)],
    [(210, 150,  16), (220, 210, 110), (130,  80,   0)],
    [(160, 160, 160), (200, 200, 220), ( 90,  90,  90)],
    [( 40, 150,  40), (130, 210, 130), ( 16,  80,  16)],
    [(145,  48, 180), (190, 140, 220), ( 80,  16, 110)],
    [(210, 105,  24), (220, 175, 110), (130,  55,   0)],
]

# ── Difficulty presets ─────────────────────────────────────────────────────────
DIFF = {
    0: dict(scroll_start=0.6, scroll_max=2.2, scroll_accel=0.0004,
            spawn_min=2.4, spawn_max=4.0, traffic_var=0.3),
    1: dict(scroll_start=1.0, scroll_max=3.5, scroll_accel=0.0007,
            spawn_min=1.3, spawn_max=2.4, traffic_var=0.6),
}

# ── Gyro tuning ───────────────────────────────────────────────────────────────
GYRO_DEAD  = 14.0   # degrees dead zone — filters out hand wobble
GYRO_SCALE = 0.055  # px per degree past dead zone
GYRO_MAX   = 2.5    # max px/tick

# ── Mini-font ─────────────────────────────────────────────────────────────────
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
    '9': [12, 21, 14], '-': [ 4,  4,  4], ':': [ 0, 10,  0],
    '!': [ 0, 23,  0], '/': [17,  4, 17],
}


def _text_width(text: str) -> int:
    return sum(len(_FONT.get(c.upper(), _FONT[' '])) + 1 for c in text) - 1


def _draw_text(frame, x, y, text, color, scale=1):
    cx = x
    for ch in text:
        cols = _FONT.get(ch.upper(), _FONT[' '])
        for ci, bits in enumerate(cols):
            for ri in range(5):
                if bits & (1 << (4 - ri)):
                    for dy in range(scale):
                        for dx in range(scale):
                            px, py = cx + ci*scale + dx, y + ri*scale + dy
                            if 0 <= px < W and 0 <= py < H:
                                frame[py, px] = color
        cx += (len(cols) + 1) * scale


def _draw_centered(frame, y, text, color, scale=1):
    w = _text_width(text) * scale
    _draw_text(frame, (W - w) // 2, y, text, color, scale)


# ── Car pixel art ─────────────────────────────────────────────────────────────
def _draw_car(frame, cx, cy, palette, w=4, h=6):
    body, wind, detail = palette
    x0 = cx - w // 2
    y0 = cy - h
    for row in range(h):
        for col in range(w):
            px, py = x0 + col, y0 + row
            if 0 <= px < W and 0 <= py < H:
                frame[py, px] = body
    # rounded corners
    for corner_x, corner_y in [(x0, y0), (x0+w-1, y0), (x0, y0+h-1), (x0+w-1, y0+h-1)]:
        if 0 <= corner_x < W and 0 <= corner_y < H:
            frame[corner_y, corner_x] = (0, 0, 0)
    # windshield
    for col in range(1, w - 1):
        px, py = x0 + col, y0 + 1
        if 0 <= px < W and 0 <= py < H:
            frame[py, px] = wind
    # rear window
    for col in range(1, w - 1):
        px, py = x0 + col, y0 + h - 2
        if 0 <= px < W and 0 <= py < H:
            frame[py, px] = wind
    # centre stripe
    mid = x0 + w // 2 - 1
    for row in range(2, h - 2):
        if 0 <= mid < W and 0 <= y0 + row < H:
            frame[y0 + row, mid] = detail


def _draw_player(frame, cx, cy, glow=0.0):
    x0 = cx - 2
    y0 = cy - PLAYER_H

    pixels = [
        (0, 2, C_PLAYER), (0, 3, C_PLAYER),
        (1, 1, C_PLAYER), (1, 2, C_PLAYER), (1, 3, C_PLAYER), (1, 4, C_PLAYER),
        (2, 1, C_PLAYER), (2, 2, C_PLAYER), (2, 3, C_PLAYER), (2, 4, C_PLAYER),
        (3, 2, C_PLAYER), (3, 3, C_PLAYER),
        (1, 0, C_PLAYER_W), (2, 0, C_PLAYER_W),
        (1, 6, C_PLAYER_W), (2, 6, C_PLAYER_W),
        (0, 1, C_PLAYER_D), (3, 1, C_PLAYER_D),
        (0, 4, C_PLAYER_D), (3, 4, C_PLAYER_D),
        (1, 3, C_PLAYER_D), (2, 3, C_PLAYER_D),
        (1, 5, C_PLAYER_D), (2, 5, C_PLAYER_D),
    ]
    t = min(1.0, glow / 0.45)  # 1.0 = full white flash, fades to 0
    for col, row, col_val in pixels:
        px, py = x0 + col, y0 + row
        if 0 <= px < W and 0 <= py < H:
            if t > 0:
                r = int(col_val[0] + (255 - col_val[0]) * t)
                g = int(col_val[1] + (255 - col_val[1]) * t)
                b = int(col_val[2] + (255 - col_val[2]) * t)
                frame[py, px] = (r, g, b)
            else:
                frame[py, px] = col_val


# ── Entities ──────────────────────────────────────────────────────────────────
class _Car:
    __slots__ = ('x', 'y', 'speed', 'palette', 'w', 'h', 'passed')

    def __init__(self, x, y, speed, palette):
        self.x       = float(x)
        self.y       = float(y)
        self.speed   = speed
        self.palette = palette
        self.w       = random.choice([3, 4, 4, 5])
        self.h       = random.choice([5, 6, 6, 7])
        self.passed  = False

    def tick(self, scroll_speed):
        self.y += scroll_speed + self.speed

    def off_screen(self):
        return self.y > H + 10


class _Fuel:
    __slots__ = ('x', 'y')

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)

    def tick(self, scroll_speed):
        self.y += scroll_speed * 0.6

    def off_screen(self):
        return self.y > H + 6

    def draw(self, frame):
        x, y = int(self.x), int(self.y)
        for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)]:
            px, py = x + ox, y + oy
            if 0 <= px < W and 0 <= py < H:
                frame[py, px] = C_FUEL


class _Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'color', 'life', 'max_life')

    def __init__(self, x, y, vx, vy, color, life):
        self.x    = float(x)
        self.y    = float(y)
        self.vx   = vx
        self.vy   = vy
        self.color    = color
        self.life     = life
        self.max_life = life

    def tick(self, dt):
        self.x  += self.vx
        self.y  += self.vy
        self.vy += 0.04   # slight gravity
        self.life -= dt

    def alive(self):
        return self.life > 0

    def draw(self, frame):
        t = self.life / self.max_life
        r = int(self.color[0] * t)
        g = int(self.color[1] * t)
        b = int(self.color[2] * t)
        px, py = int(self.x), int(self.y)
        if 0 <= px < W and 0 <= py < H:
            frame[py, px] = (r, g, b)


# ── Main mode ─────────────────────────────────────────────────────────────────
class RoadFighter(BaseMode):

    @staticmethod
    def metadata():
        return {
            "name":        "Road Fighter",
            "description": "Dodge traffic on an endless road. Tilt phone or use d-pad.",
            "category":    "games",
        }

    def __init__(self):
        self._difficulty   = 0
        self._control      = 0   # 0=D-pad  1=Gyro  2=Both
        self._hi_score     = 0
        self._state        = "title"
        self._gyro_gamma    = 0.0
        self._gyro_fresh    = 0.0
        self._gyro_baseline = None   # calibrated on first gyro reading
        self._dpad         = 0
        self._speed_boost  = 0
        self._title_scroll = 0.0
        self._paused       = False
        self._particles: list[_Particle] = []
        self._explode_t    = 0.0
        self._fuel_glow    = 0.0   # seconds remaining for fuel-collect glow

    # ── BaseMode ──────────────────────────────────────────────────────────────
    def start(self):
        self._state        = "title"
        self._title_scroll = 0.0
        self._paused       = False
        self._bg_cars = [_Car(
            random.randint(ROAD_L + 4, ROAD_R - 4),
            random.uniform(-H, 0),
            random.uniform(-0.2, 0.2),
            random.choice(TRAFFIC_PALETTES),
        ) for _ in range(4)]

    def stop(self):
        pass

    def tick(self, dt):
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        self._gyro_fresh = max(0.0, self._gyro_fresh - dt)

        if self._state == "title":
            self._tick_title(dt, frame)
        elif self._state == "playing":
            if self._paused:
                self._draw_paused(frame)
            else:
                self._tick_game(dt, frame)
        elif self._state == "exploding":
            self._tick_exploding(dt, frame)
        elif self._state == "game_over":
            self._tick_game_over(dt, frame)
        return frame

    def handle_input(self, player, action):
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

        if self._state == "exploding":
            return   # no input during explosion

        # Playing (possibly paused)
        if action == "select":
            self._paused = not self._paused
            return

        if self._paused:
            if action == "start":
                self._paused = False
            return

        if action == "left":
            self._dpad = -1
        elif action == "right":
            self._dpad = 1
        elif action == "up":
            self._speed_boost = 1
        elif action == "down":
            self._speed_boost = -1
        elif action == "start":
            self._end_game()

    def handle_gyro(self, gamma, beta):
        # In landscape mode (how the overlay is held), beta is the left/right tilt axis
        if self._gyro_baseline is None:
            self._gyro_baseline = beta
        self._gyro_gamma = beta - self._gyro_baseline
        self._gyro_fresh = 0.5

    def is_over(self):
        return self._state == "game_over"

    def get_settings(self):
        return [
            {
                "key": "difficulty", "label": "Difficulty", "type": "select",
                "options": [{"value": 0, "label": "Easy"},
                            {"value": 1, "label": "Hard"}],
                "value": self._difficulty,
            },
            {
                "key": "control", "label": "Control", "type": "select",
                "options": [{"value": 0, "label": "D-pad"},
                            {"value": 1, "label": "Gyro"},
                            {"value": 2, "label": "Both"}],
                "value": self._control,
            },
        ]

    def apply_setting(self, key, value):
        if key == "difficulty":
            self._difficulty = max(0, min(1, int(value)))
        elif key == "control":
            self._control = max(0, min(2, int(value)))

    # ── Game init ─────────────────────────────────────────────────────────────
    def _new_game(self):
        cfg = DIFF[self._difficulty]
        self._scroll      = cfg["scroll_start"]
        self._scroll_max  = cfg["scroll_max"]
        self._scroll_acc  = cfg["scroll_accel"]
        self._spawn_min   = cfg["spawn_min"]
        self._spawn_max   = cfg["spawn_max"]
        self._traffic_var = cfg["traffic_var"]

        self._player_x    = float(CENTER)
        self._scroll_y    = 0.0
        self._cars: list[_Car]   = []
        self._fuels: list[_Fuel] = []
        self._score       = 0
        self._spawn_t     = random.uniform(self._spawn_min, self._spawn_max)
        self._fuel_t      = random.uniform(5.0, 10.0)
        self._speed_boost   = 0
        self._dpad          = 0
        self._paused        = False
        self._gyro_baseline = None
        self._fuel_glow     = 0.0
        self._state         = "playing"

    # ── Tick helpers ──────────────────────────────────────────────────────────
    def _tick_title(self, dt, frame):
        self._title_scroll = (self._title_scroll + 0.5) % H
        self._draw_road(frame, self._title_scroll)
        for c in self._bg_cars:
            c.tick(0.5)
            if c.off_screen():
                c.x = random.randint(ROAD_L + 4, ROAD_R - 4)
                c.y = -8
            _draw_car(frame, int(c.x), int(c.y), c.palette, c.w, c.h)

        # Darken the background so text is readable
        frame[:] = (frame.astype(np.float32) * 0.32).astype(np.uint8)

        _draw_centered(frame,  5, "ROAD",        C_TITLE,    scale=2)
        _draw_centered(frame, 17, "FIGHTER",     C_TITLE,    scale=2)
        _draw_centered(frame, 33, "PRESS START", C_SUBTITLE)
        diff_label = ("EASY", "HARD")[self._difficulty]
        diff_col   = (80, 200, 100) if self._difficulty == 0 else (220, 80, 60)
        _draw_centered(frame, 43, diff_label, diff_col)
        if self._hi_score > 0:
            _draw_centered(frame, 53, f"HI {self._hi_score}", C_SCORE)

    def _tick_game(self, dt, frame):
        # Speed ramps up over time — players feel it after ~20-30 s
        boost_effect = self._speed_boost * 0.25
        self._speed_boost = 0
        effective_scroll = max(0.3, self._scroll + boost_effect)
        self._scroll = min(self._scroll_max, self._scroll + self._scroll_acc)
        self._scroll_y = (self._scroll_y + effective_scroll) % H

        # Steer
        use_gyro = (self._control == 1 or self._control == 2) and self._gyro_fresh > 0
        use_dpad = (self._control == 0 or self._control == 2)

        car_vx = 0.0
        if use_gyro:
            g = self._gyro_gamma
            if abs(g) > GYRO_DEAD:
                sign = 1 if g > 0 else -1
                car_vx = sign * (abs(g) - GYRO_DEAD) * GYRO_SCALE
                car_vx = max(-GYRO_MAX, min(GYRO_MAX, car_vx))
        if use_dpad and self._dpad != 0:
            car_vx += self._dpad * 1.8   # additive: works alongside gyro in Both mode
        self._dpad = 0

        self._player_x = max(PLAYER_MIN_X,
                             min(PLAYER_MAX_X, self._player_x + car_vx))

        # Spawn traffic
        self._spawn_t -= dt
        if self._spawn_t <= 0:
            self._spawn_t = random.uniform(self._spawn_min, self._spawn_max)
            lanes = [ROAD_L + 6, CENTER, ROAD_R - 6]
            lx  = random.choice(lanes) + random.randint(-3, 3)
            spd = random.uniform(-self._traffic_var, self._traffic_var)
            self._cars.append(_Car(lx, -8, spd, random.choice(TRAFFIC_PALETTES)))

        # Spawn fuel
        self._fuel_t -= dt
        if self._fuel_t <= 0:
            self._fuel_t = random.uniform(6.0, 12.0)
            fx = random.randint(ROAD_L + 4, ROAD_R - 4)
            self._fuels.append(_Fuel(fx, -6))

        # Update
        for c in self._cars:
            c.tick(effective_scroll)
        for f in self._fuels:
            f.tick(effective_scroll)

        self._score += 1
        for c in self._cars:
            if not c.passed and c.y > PLAYER_Y + PLAYER_H:
                c.passed = True
                self._score += 15

        self._cars  = [c for c in self._cars  if not c.off_screen()]
        self._fuels = [f for f in self._fuels if not f.off_screen()]

        # Collision: traffic
        px0 = int(self._player_x) - PLAYER_W // 2
        px1 = int(self._player_x) + PLAYER_W // 2
        py0 = PLAYER_Y - PLAYER_H
        py1 = PLAYER_Y
        for c in self._cars:
            cx0 = int(c.x) - c.w // 2
            cx1 = int(c.x) + c.w // 2
            cy0 = int(c.y) - c.h
            cy1 = int(c.y)
            if px0 < cx1 and px1 > cx0 and py0 < cy1 and py1 > cy0:
                self._start_explosion()
                break

        # Collision: fuel
        for f in list(self._fuels):
            if abs(self._player_x - f.x) < 4 and abs(PLAYER_Y - f.y) < 6:
                self._score += 30
                self._fuel_glow = 0.45
                self._fuels.remove(f)

        self._fuel_glow = max(0.0, self._fuel_glow - dt)

        # Draw
        if self._state == "playing":   # might have just triggered explosion
            self._draw_road(frame, self._scroll_y)
            for f in self._fuels:
                f.draw(frame)
            for c in self._cars:
                _draw_car(frame, int(c.x), int(c.y), c.palette, c.w, c.h)
            _draw_player(frame, int(self._player_x), PLAYER_Y, self._fuel_glow)
            self._draw_hud(frame)

    def _tick_exploding(self, dt, frame):
        self._explode_t -= dt
        self._draw_road(frame, self._scroll_y)
        for p in self._particles:
            p.tick(dt)
            p.draw(frame)
        self._particles = [p for p in self._particles if p.alive()]
        if self._explode_t <= 0:
            self._state = "game_over"

    def _tick_game_over(self, dt, frame):
        _draw_centered(frame, 14, "GAME",          C_GAMEOVER, scale=2)
        _draw_centered(frame, 28, "OVER",          C_GAMEOVER, scale=2)
        _draw_centered(frame, 44, str(self._score), C_TITLE)
        _draw_centered(frame, 54, "START",          C_SUBTITLE)

    def _draw_paused(self, frame):
        self._draw_road(frame, self._scroll_y)
        frame[:] = (frame.astype(np.float32) * 0.25).astype(np.uint8)
        _draw_player(frame, int(self._player_x), PLAYER_Y)
        _draw_centered(frame, 26, "PAUSE", C_PAUSE, scale=2)
        _draw_centered(frame, 40, "SELECT", C_SUBTITLE)

    # ── Explosion ─────────────────────────────────────────────────────────────
    def _start_explosion(self):
        if self._score > self._hi_score:
            self._hi_score = self._score
        cx, cy = int(self._player_x), PLAYER_Y - PLAYER_H // 2
        EXPLOSION_COLORS = [
            (255, 200,  50), (255, 140,  20), (255,  60,  10),
            (220, 220, 220), (255, 255, 120),
        ]
        self._particles = []
        for _ in range(20):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(0.5, 2.5)
            col   = random.choice(EXPLOSION_COLORS)
            life  = random.uniform(0.35, 0.75)
            self._particles.append(_Particle(
                cx, cy,
                math.cos(angle) * speed,
                math.sin(angle) * speed - 0.5,
                col, life,
            ))
        self._explode_t = 0.8
        self._state     = "exploding"

    # ── Road drawing ──────────────────────────────────────────────────────────
    def _draw_road(self, frame, scroll):
        for y in range(H):
            stripe = int((y - scroll) // 4) % 2
            grass_col = C_GRASS_L if stripe else C_GRASS_D
            for x in range(W):
                if x < ROAD_L - 1:
                    frame[y, x] = grass_col
                elif x == ROAD_L - 1:
                    frame[y, x] = C_SHOULDER
                elif x == ROAD_L:
                    frame[y, x] = C_LINE
                elif x < ROAD_R:
                    frame[y, x] = C_ROAD
                elif x == ROAD_R:
                    frame[y, x] = C_LINE
                elif x == ROAD_R + 1:
                    frame[y, x] = C_SHOULDER
                else:
                    frame[y, x] = grass_col

        dash_period = 8
        for y in range(H):
            if int(y - scroll) % dash_period < 4:
                if 0 <= CENTER < W:
                    frame[y, CENTER]     = C_DASH
                    frame[y, CENTER + 1] = C_DASH

    # ── HUD ───────────────────────────────────────────────────────────────────
    def _draw_hud(self, frame):
        speed_range = self._scroll_max - DIFF[self._difficulty]["scroll_start"] + 0.01
        speed_frac  = (self._scroll - DIFF[self._difficulty]["scroll_start"]) / speed_range
        bar_h = max(1, int(speed_frac * 8))
        for i in range(bar_h):
            fy = 8 - i
            frame[fy, W - 3] = C_SPEED_HI
            frame[fy, W - 2] = C_SPEED_HI

        _draw_text(frame, 1, 1, str(self._score), C_SCORE)

        # Gyro live indicator: small dot when gyro active
        if self._gyro_fresh > 0 and (self._control == 1 or self._control == 2):
            frame[1, W - 5] = (60, 200, 160)

    # ── End game (via start button, not collision) ─────────────────────────────
    def _end_game(self):
        if self._score > self._hi_score:
            self._hi_score = self._score
        self._state = "game_over"
