import math
import random
import numpy as np
from base_mode import BaseMode

# ── Layout ────────────────────────────────────────────────────────────────────
W, H      = 64, 64
PAD_W     = 2
PAD_LX    = 3            # left paddle left edge
PAD_RX    = W - PAD_W - PAD_LX   # = 59, right paddle left edge
BALL_SIZE = 2

# ── Physics ───────────────────────────────────────────────────────────────────
BALL_SPEED_INIT = 44.0   # px/s
BALL_SPEED_MAX  = 80.0   # px/s cap
BALL_SPEED_INC  = 0.06   # fraction speed increase per paddle bounce
PAD_MOVE        = 5      # px per discrete input event

# Per difficulty 0=Easy / 1=Medium / 2=Hard
PAD_H_DIFF = [14,   10,   8   ]  # paddle height in px
CPU_SPEED  = [30.0, 44.0, 66.0]  # CPU tracking speed px/s
CPU_ERR    = [14,   5,    1   ]  # random positional error px

# ── Colours ───────────────────────────────────────────────────────────────────
C_P1   = (0,   220, 80 )
C_P2   = (70,  130, 255)
C_CPU  = (255, 140, 30 )
C_BALL = (255, 255, 255)
C_NET  = (28,  28,  48 )

# ── Font ──────────────────────────────────────────────────────────────────────
# column-bitmasks: bit4=top, bit0=bottom; draw with (1 << (4-ri))
_FONT: dict[str, list[int]] = {
    ' ': [0, 0, 0],
    'A': [15,20,15], 'B': [31,21,10], 'C': [14,17,17],
    'D': [31,17,14], 'E': [31,21,17], 'F': [31,20,16],
    'G': [14,21,23], 'H': [31, 4,31], 'I': [17,31,17],
    'J': [ 2,17,30], 'K': [31, 4,27], 'L': [31, 1, 1],
    'M': [31,24, 4,24,31], 'N': [31,8,4,31],
    'O': [14,17,14], 'P': [31,20,24], 'Q': [14,17,15],
    'R': [31,20,11], 'S': [ 9,21,18], 'T': [16,31,16],
    'U': [30, 1,30], 'V': [28, 3,28], 'W': [31,2,4,2,31],
    'X': [27, 4,27], 'Y': [24, 7,24], 'Z': [19,21, 9],
    '0': [14,17,14], '1': [ 9,31, 1], '2': [23,21,29],
    '3': [21,21,31], '4': [28, 4,31], '5': [29,21,23],
    '6': [31,21, 7], '7': [16,19,28], '8': [10,21,10],
    '9': [12,21,14], '-': [4, 4, 4],
}

def _tw(text: str) -> int:
    return sum(len(_FONT.get(c.upper(), _FONT[' '])) + 1 for c in text) - 1

def _dt(frame, x: int, y: int, text: str, color, scale: int = 1):
    cx = x
    for ch in text:
        cols = _FONT.get(ch.upper(), _FONT[' '])
        for ci, bits in enumerate(cols):
            for ri in range(5):
                if bits & (1 << (4 - ri)):
                    for dy in range(scale):
                        for dx in range(scale):
                            px, py = cx + ci*scale + dx, y + ri*scale + dy
                            if 0 <= px < 64 and 0 <= py < 64:
                                frame[py, px] = color
        cx += (len(cols) + 1) * scale

def _dc(frame, y: int, text: str, color, scale: int = 1):
    _dt(frame, (64 - _tw(text) * scale) // 2, y, text, color, scale)


# ── Mode ──────────────────────────────────────────────────────────────────────
class Pong(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name":        "Pong",
            "description": "Classic paddle game — 1 or 2 players",
            "category":    "games",
        }

    def __init__(self):
        self._players    = 1
        self._difficulty = 1   # 0=Easy  1=Medium  2=Hard
        self._win_score  = 7
        self._control        = 0   # 0=D-pad  1=Rotation
        self._gyro_beta      = 45.0
        self._gyro_beta_last = 45.0
        self._full_reset()

    @property
    def _pad_h(self) -> int:
        return PAD_H_DIFF[self._difficulty]

    # ── State reset ───────────────────────────────────────────────────────────
    def _full_reset(self) -> None:
        self._score      = [0, 0]
        ph = PAD_H_DIFF[self._difficulty]
        self._pad_y      = [float(H // 2 - ph // 2),
                            float(H // 2 - ph // 2)]
        self._waiting    = True
        self._paused     = False
        self._game_over  = False
        self._winner     = -1
        self._particles: list = []
        self._serve_t    = 0.0
        self._refresh_cpu_err()
        self._spawn_ball(0)

    def _refresh_cpu_err(self) -> None:
        err = CPU_ERR[self._difficulty]
        self._cpu_err = random.uniform(-err, err)

    def _spawn_ball(self, serve_to: int) -> None:
        self._ball  = [float(W // 2 - 1), float(H // 2 - 1)]
        angle = random.uniform(-22, 22)
        vx = BALL_SPEED_INIT * math.cos(math.radians(angle))
        vy = BALL_SPEED_INIT * math.sin(math.radians(angle))
        self._bv    = [vx if serve_to == 0 else -vx, vy]
        self._trail: list = []
        self._serve_t = 1.2   # pre-launch pause
        self._refresh_cpu_err()  # fresh error on every serve

    # ── BaseMode ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._full_reset()

    def stop(self)  -> None:  pass

    def handle_gyro(self, gamma: float, beta: float) -> None:
        # Reject spikes — gimbal lock can cause sudden jumps of 90°+
        if abs(beta - self._gyro_beta_last) < 20.0:
            self._gyro_beta = beta
        self._gyro_beta_last = beta

    def tick(self, dt: float) -> np.ndarray:
        self._tick_particles(dt)

        # Rotation paddle: beta mapped over safe range 5°–75°, smoothed
        if self._control == 1 and not self._waiting \
                and not self._game_over and not self._paused:
            ph      = self._pad_h
            beta    = max(5.0, min(75.0, self._gyro_beta))
            frac    = 1.0 - (beta - 5.0) / 70.0        # 5°=bottom  75°=top
            target  = frac * (H - ph)
            # Smooth toward target — damps twitchiness and hides gimbal jumps
            self._pad_y[0] += (target - self._pad_y[0]) * 0.25
            self._pad_y[0]  = max(0.0, min(float(H - ph), self._pad_y[0]))

        if self._waiting or self._game_over or self._paused:
            return self._draw()

        if self._serve_t > 0:
            self._serve_t -= dt
            return self._draw()

        # ── CPU ───────────────────────────────────────────────────────────────
        ph = self._pad_h
        if self._players == 1:
            target = self._ball[1] - ph / 2 + self._cpu_err
            step   = CPU_SPEED[self._difficulty] * dt
            diff   = target - self._pad_y[1]
            self._pad_y[1] += max(-step, min(step, diff))
            self._pad_y[1]  = max(0.0, min(float(H - ph), self._pad_y[1]))

        # ── Ball ──────────────────────────────────────────────────────────────
        self._trail.append((self._ball[0], self._ball[1]))
        if len(self._trail) > 5:
            self._trail.pop(0)

        self._ball[0] += self._bv[0] * dt
        self._ball[1] += self._bv[1] * dt

        # Wall bounce (top / bottom)
        if self._ball[1] < 0:
            self._ball[1] = 0.0
            self._bv[1]   = abs(self._bv[1])
        elif self._ball[1] + BALL_SIZE > H:
            self._ball[1] = H - BALL_SIZE
            self._bv[1]   = -abs(self._bv[1])

        bx, by = self._ball[0], self._ball[1]

        # Left paddle hit
        if (self._bv[0] < 0
                and bx <= PAD_LX + PAD_W + 2
                and bx + BALL_SIZE >= PAD_LX
                and by + BALL_SIZE > self._pad_y[0]
                and by < self._pad_y[0] + ph):
            self._ball[0] = PAD_LX + PAD_W
            self._bounce_off(0)

        # Right paddle hit
        if (self._bv[0] > 0
                and bx + BALL_SIZE >= PAD_RX - 2
                and bx <= PAD_RX + PAD_W
                and by + BALL_SIZE > self._pad_y[1]
                and by < self._pad_y[1] + ph):
            self._ball[0] = PAD_RX - BALL_SIZE
            self._bounce_off(1)

        # Scoring
        if self._ball[0] + BALL_SIZE < 0:
            self._point(1)
        elif self._ball[0] > W:
            self._point(0)

        return self._draw()

    def _bounce_off(self, side: int) -> None:
        ph       = self._pad_h
        pad_ctr  = self._pad_y[side] + ph / 2
        ball_ctr = self._ball[1] + BALL_SIZE / 2
        rel      = max(-1.0, min(1.0, (ball_ctr - pad_ctr) / (ph / 2)))
        spd      = min(BALL_SPEED_MAX,
                       math.hypot(self._bv[0], self._bv[1]) * (1 + BALL_SPEED_INC))
        angle    = rel * 52   # ±52° from horizontal
        vx       = spd * math.cos(math.radians(angle))
        vy       = spd * math.sin(math.radians(angle))
        self._bv = [vx if side == 0 else -vx, vy]
        if side == 1 and self._players == 1:
            self._refresh_cpu_err()

    def _point(self, scorer: int) -> None:
        self._score[scorer] += 1
        self._emit_particles(scorer, 20)
        if self._score[scorer] >= self._win_score:
            self._game_over = True
            self._winner    = scorer
            self._emit_particles(scorer, 30)   # extra burst on game end
        else:
            self._spawn_ball(1 - scorer)       # loser serves

    # ── Particles ─────────────────────────────────────────────────────────────
    def _emit_particles(self, side: int, n: int) -> None:
        col = C_P1 if side == 0 else (C_CPU if self._players == 1 else C_P2)
        cx  = W // 4 if side == 0 else 3 * W // 4
        for _ in range(n):
            a   = random.uniform(0, 2 * math.pi)
            spd = random.uniform(18, 75)
            self._particles.append({
                'x': float(cx), 'y': float(H // 2),
                'vx': spd * math.cos(a), 'vy': spd * math.sin(a),
                'life': random.uniform(0.5, 1.2),
                'col': col,
            })

    def _tick_particles(self, dt: float) -> None:
        alive = []
        for p in self._particles:
            p['x']    += p['vx'] * dt
            p['y']    += p['vy'] * dt
            p['vy']   += 60 * dt   # gravity
            p['life'] -= dt
            if p['life'] > 0:
                alive.append(p)
        self._particles = alive

    # ── Drawing ───────────────────────────────────────────────────────────────
    def _draw(self) -> np.ndarray:
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        if self._waiting:
            return self._draw_title(frame)
        if self._game_over:
            return self._draw_gameover(frame)
        self._draw_field(frame)
        self._draw_scores(frame)
        self._draw_paddles(frame)
        self._draw_ball(frame)
        self._draw_particles(frame)
        if self._paused:
            self._draw_pause(frame)
        return frame

    def _draw_field(self, frame: np.ndarray) -> None:
        pass  # no center line — cleaner look

    def _draw_scores(self, frame: np.ndarray) -> None:
        s0   = str(self._score[0])
        s1   = str(self._score[1])
        p2c  = C_CPU if self._players == 1 else C_P2
        # Right-align P1 left of centre, left-align P2 right of centre
        _dt(frame, W // 2 - 5 - _tw(s0) * 2, 2, s0, C_P1, scale=2)
        _dt(frame, W // 2 + 5,                2, s1, p2c,  scale=2)

    def _draw_paddles(self, frame: np.ndarray) -> None:
        ph = self._pad_h

        def _pad(py: float, lx: int, col: tuple) -> None:
            y0 = max(0, int(py))
            y1 = min(H, int(py) + ph)
            frame[y0:y1, lx:lx + PAD_W] = col
            dim = tuple(v // 5 for v in col)
            if y0 > 0: frame[y0 - 1, lx:lx + PAD_W] = dim
            if y1 < H: frame[y1,     lx:lx + PAD_W] = dim

        _pad(self._pad_y[0], PAD_LX, C_P1)
        _pad(self._pad_y[1], PAD_RX, C_CPU if self._players == 1 else C_P2)

    def _draw_ball(self, frame: np.ndarray) -> None:
        total = len(self._trail) + 1
        for i, (tx, ty) in enumerate(self._trail):
            t   = (i + 1) / total * 0.5
            bx2, by2 = int(tx), int(ty)
            if 0 <= bx2 < W - 1 and 0 <= by2 < H - 1:
                frame[by2:by2 + BALL_SIZE, bx2:bx2 + BALL_SIZE] = (
                    int(255 * t), int(255 * t), int(255 * t))
        bx, by = int(self._ball[0]), int(self._ball[1])
        if 0 <= bx < W - 1 and 0 <= by < H - 1:
            frame[by:by + BALL_SIZE, bx:bx + BALL_SIZE] = C_BALL

    def _draw_particles(self, frame: np.ndarray) -> None:
        for p in self._particles:
            px, py = int(p['x']), int(p['y'])
            if 0 <= px < W and 0 <= py < H:
                t   = min(1.0, p['life'])
                col = tuple(int(v * t) for v in p['col'])
                frame[py, px] = col

    def _draw_title(self, frame: np.ndarray) -> np.ndarray:
        frame[0:2,   :] = (0, 50, 120)
        frame[62:64, :] = (0, 50, 120)
        _dc(frame,  9, "PONG", (0, 180, 255), scale=2)
        if self._players == 1:
            diff_label = ["EASY", "MED", "HARD"][self._difficulty]
            _dc(frame, 30, "1P VS CPU",  (140, 140, 140))
            _dc(frame, 38, diff_label,   C_CPU)
        else:
            _dc(frame, 34, "2 PLAYERS", (140, 140, 140))
        _dc(frame, 53, "START", (65, 65, 65))
        return frame

    def _draw_gameover(self, frame: np.ndarray) -> np.ndarray:
        # Black background
        w  = self._winner
        wc = C_P1 if w == 0 else (C_CPU if self._players == 1 else C_P2)

        # Coloured border on all edges
        frame[0:2,   :] = wc
        frame[62:64, :] = wc
        frame[:,  0:2]  = wc
        frame[:, 62:64] = wc

        # Particles behind text
        self._draw_particles(frame)

        name = "P1" if w == 0 else ("CPU" if self._players == 1 else "P2")
        _dc(frame,  6, name,   wc,            scale=2)
        _dc(frame, 18, "WINS", wc,            scale=2)
        frame[31, 8:56] = tuple(v // 3 for v in wc)
        sc = f"{self._score[0]}-{self._score[1]}"
        _dc(frame, 35, sc, (180, 180, 180))
        _dc(frame, 53, "START", (60, 60, 60))
        return frame

    def _draw_pause(self, frame: np.ndarray) -> None:
        frame[:] = (frame * 0.35).astype(np.uint8)
        _dc(frame, 22, "PAUSED", (180, 180, 180))
        _dc(frame, 34, "SELECT", (100, 100, 100))
        _dc(frame, 41, "RESUME", (100, 100, 100))

    # ── Input ─────────────────────────────────────────────────────────────────
    def handle_input(self, player: int, action: str) -> None:
        if action == "start":
            if self._waiting or self._game_over:
                self._full_reset()
                self._waiting = False
            else:
                self._paused = not self._paused
            return
        if action == "select":
            if not self._waiting and not self._game_over:
                self._paused = not self._paused
            return

        if self._waiting or self._game_over or self._paused:
            return

        # In 1P mode player 1 input controls right (CPU) paddle — ignore
        if self._players == 1 and player == 1:
            return

        pad = player  # player 0 → left paddle, player 1 → right paddle
        if action == "up":
            self._pad_y[pad] = max(0.0, self._pad_y[pad] - PAD_MOVE)
        elif action == "down":
            self._pad_y[pad] = min(float(H - self._pad_h), self._pad_y[pad] + PAD_MOVE)

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings(self) -> list[dict]:
        return [
            {
                "key":     "control",
                "label":   "P1 Control",
                "type":    "select",
                "value":   self._control,
                "options": [
                    {"value": 0, "label": "D-pad"},
                    {"value": 1, "label": "Rotation (tilt)"},
                ],
            },
            {
                "key":     "players",
                "label":   "Players",
                "type":    "select",
                "value":   self._players,
                "options": [
                    {"value": 1, "label": "1 Player (vs CPU)"},
                    {"value": 2, "label": "2 Players"},
                ],
            },
            {
                "key":     "difficulty",
                "label":   "CPU Difficulty",
                "type":    "select",
                "value":   self._difficulty,
                "options": [
                    {"value": 0, "label": "Easy"},
                    {"value": 1, "label": "Medium"},
                    {"value": 2, "label": "Hard"},
                ],
            },
            {
                "key":     "win_score",
                "label":   "First to",
                "type":    "select",
                "value":   self._win_score,
                "options": [
                    {"value": 5,  "label": "5 points"},
                    {"value": 7,  "label": "7 points"},
                    {"value": 10, "label": "10 points"},
                ],
            },
        ]

    def apply_setting(self, key: str, value) -> None:
        if key == "control":
            self._control = int(value)
        elif key == "players":
            self._players = int(value)
            self._full_reset()
        elif key == "difficulty":
            self._difficulty = int(value)
        elif key == "win_score":
            self._win_score = int(value)
