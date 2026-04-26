import math
import random
from collections import deque

import numpy as np
from base_mode import BaseMode

CELL = 2
GW   = 64 // CELL   # 32
GH   = 64 // CELL   # 32

DIRS = {
    "up":    ( 0, -1),
    "down":  ( 0,  1),
    "left":  (-1,  0),
    "right": ( 1,  0),
}

C_P1   = (0,   220, 60)
C_P2   = (30,  120, 255)
C_FOOD = (255, 60,  0)

# ── 3-5×5 font ───────────────────────────────────────────────────────────────
# Each entry: list of column bitmasks (left→right).
# Each bitmask: 5 bits. bit4 = top pixel, bit0 = bottom pixel.
# Encoding: value = sum of (1 << (4 - row)) for each lit row (row 0=top).
_FONT: dict[str, list[int]] = {
    ' ': [0, 0, 0],          # 3-wide space
    'A': [15, 20, 15],       # .#. / #.# / ### / #.# / #.#
    'B': [31, 21, 10],       # ##. / #.# / ##. / #.# / ##.
    'C': [14, 17, 17],       # .## / #.. / #.. / #.. / .##
    'D': [31, 17, 14],       # ##. / #.# / #.# / #.# / ##.
    'E': [31, 21, 17],       # ### / #.. / ##. / #.. / ###
    'F': [31, 20, 16],       # ### / #.. / ##. / #.. / #..
    'G': [14, 21, 23],       # .## / #.. / ### / #.# / .##
    'H': [31, 4,  31],       # #.# / #.# / ### / #.# / #.#
    'I': [17, 31, 17],       # ### / .#. / .#. / .#. / ###
    'J': [2,  17, 30],       # .## / ..# / ..# / #.# / .#.
    'K': [31, 4,  27],       # #.# / #.# / ##. / #.# / #.#
    'L': [31, 1,  1],        # #.. / #.. / #.. / #.. / ###
    'M': [31, 24, 4, 24, 31],# #.# / ##.## / #.#.# / #...# / #...#
    'N': [31, 8,  4,  31],   # #..# / ##.# / #.## / #..# / #..#
    'O': [14, 17, 14],       # .#. / #.# / #.# / #.# / .#.
    'P': [31, 20, 24],       # ### / #.# / ##. / #.. / #..
    'Q': [14, 17, 15],       # .#. / #.# / #.# / #.# / .##
    'R': [31, 20, 11],       # ##. / #.# / ##. / #.# / #.#
    'S': [9,  21, 18],       # .## / #.. / .#. / ..# / ##.
    'T': [16, 31, 16],       # ### / .#. / .#. / .#. / .#.
    'U': [30, 1,  30],       # #.# / #.# / #.# / #.# / .#.
    'V': [28, 3,  28],       # #.# / #.# / #.# / .#. / .#.
    'W': [31, 2,  4,  2, 31],# #...# / #...# / #.#.# / ##.## / #...#
    'X': [27, 4,  27],       # #.# / #.# / .#. / #.# / #.#
    'Y': [24, 7,  24],       # #.# / #.# / .#. / .#. / .#.
    'Z': [19, 21, 9],        # ##. / ..# / .#. / #.. / ###
    '0': [14, 17, 14],       # .#. / #.# / #.# / #.# / .#.
    '1': [9,  31, 1],        # .#. / ##. / .#. / .#. / ###
    '2': [23, 21, 29],       # ### / ..# / ### / #.. / ###
    '3': [21, 21, 31],       # ### / ..# / ### / ..# / ###
    '4': [28, 4,  31],       # #.# / #.# / ### / ..# / ..#
    '5': [29, 21, 23],       # ### / #.. / ### / ..# / ###
    '6': [31, 21, 7],        # ##. / #.. / ### / #.# / ###
    '7': [16, 19, 28],       # ### / ..# / ..# / .#. / .#.
    '8': [10, 21, 10],       # .#. / #.# / .#. / #.# / .#.
    '9': [12, 21, 14],       # .#. / #.# / ### / ..# / .#.
    '-': [4,  4,  4],        # ... / ... / ### / ... / ...
    '!': [0,  23, 0],        # .#. / .#. / .#. / ... / .#.
    ':': [0,  10, 0],        # ... / .#. / ... / .#. / ...
}

_CHAR_W = 5   # max column count
_CHAR_H = 5


def _char_width(ch: str) -> int:
    cols = _FONT.get(ch.upper(), _FONT[' '])
    return len(cols) + 1   # +1 gap


def _text_width(text: str) -> int:
    return sum(_char_width(c) for c in text) - 1


def _draw_text(frame: np.ndarray, x: int, y: int, text: str, color, scale: int = 1) -> None:
    cx = x
    for ch in text:
        cols = _FONT.get(ch.upper(), _FONT[' '])
        for ci, bits in enumerate(cols):
            for ri in range(_CHAR_H):
                if bits & (1 << (4 - ri)):
                    for dy in range(scale):
                        for dx in range(scale):
                            px = cx + ci * scale + dx
                            py = y  + ri * scale + dy
                            if 0 <= px < 64 and 0 <= py < 64:
                                frame[py, px] = color
        cx += (len(cols) + 1) * scale


def _draw_centered(frame: np.ndarray, y: int, text: str, color, scale: int = 1) -> None:
    w = _text_width(text) * scale
    _draw_text(frame, (64 - w) // 2, y, text, color, scale)


# ── Mode ──────────────────────────────────────────────────────────────────────
class Snake(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Snake",
            "description": "Classic snake — 1 or 2 players. Press Start to begin.",
            "category": "games",
        }

    # Speed ramps from START_INTERVAL down to MIN_INTERVAL as food is eaten.
    _START_INTERVAL = 0.20   # slow at the beginning
    _MIN_INTERVAL   = 0.07   # fastest possible (~14 steps/sec)
    _SPEED_DECAY    = 0.005  # interval reduction per food eaten

    def __init__(self):
        self._n_players  = 1
        self._difficulty = 0   # 0=Normal, 1=Hard, 2=Very Hard
        self._wall_time  = 0.0
        self._reset()

    # ── Reset ─────────────────────────────────────────────────────────────────
    def _reset(self) -> None:
        self._snakes: list[deque] = [
            deque([(GW // 4,     GH // 2)]),
            deque([(3 * GW // 4, GH // 2)]),
        ]
        self._dirs         = [(1, 0), (-1, 0)]
        self._queued       = [(1, 0), (-1, 0)]
        self._scores       = [0, 0]
        self._food: tuple[int, int] = (GW // 2, GH // 2)
        self._place_food()
        self._game_over    = False
        self._winner       = -2   # -2=no result, -1=draw, 0=P1, 1=P2
        self._timer        = 0.0
        self._step_interval = self._START_INTERVAL
        self._score_flash  = 0.0
        self._food_pulse   = 0.0
        self._paused       = False
        self._waiting      = True
        # Feed pulses: list per player of segment positions (float, 0=head→tail)
        self._pulses: list[list[float]] = [[], []]

    def start(self) -> None:
        self._reset()

    def stop(self) -> None:
        pass

    # ── Food ──────────────────────────────────────────────────────────────────
    def _place_food(self) -> None:
        occupied: set[tuple[int, int]] = set()
        for s in self._snakes:
            occupied.update(s)
        # Exclude wall cells so food never spawns under a wall
        if self._difficulty >= 1:
            for x in range(GW):
                occupied.add((x, 0))
                occupied.add((x, GH - 1))
        if self._difficulty >= 2:
            for y in range(GH):
                occupied.add((0, y))
                occupied.add((GW - 1, y))
        candidates = [(x, y) for x in range(GW) for y in range(GH) if (x, y) not in occupied]
        self._food = random.choice(candidates) if candidates else (GW // 2, GH // 2)

    # ── Step ──────────────────────────────────────────────────────────────────
    def _step(self) -> None:
        np_ = self._n_players
        self._dirs = list(self._queued)

        wall_tb   = self._difficulty >= 1   # top/bottom walls
        wall_side = self._difficulty >= 2   # left/right walls

        new_heads = []
        alive = [True] * np_

        for p in range(np_):
            hx, hy = self._snakes[p][0]
            dx, dy = self._dirs[p]
            nx, ny = hx + dx, hy + dy
            # Wall cells are the edge rows/cols themselves — die on entry, not just past edge
            if wall_tb   and not (1 <= ny < GH - 1): alive[p] = False
            if wall_side and not (1 <= nx < GW - 1): alive[p] = False
            # For normal (no wall) mode, snake wraps via modulo
            if not wall_tb   and not (0 <= ny < GH): ny %= GH
            if not wall_side and not (0 <= nx < GW): nx %= GW
            new_heads.append((nx, ny))

        for p in range(np_):
            body = list(self._snakes[p])[:-1]
            if new_heads[p] in body:
                alive[p] = False

        if np_ == 2:
            for p in range(2):
                if new_heads[p] in self._snakes[1 - p]:
                    alive[p] = False
            if new_heads[0] == new_heads[1]:
                alive[0] = alive[1] = False

        if np_ == 1:
            if not alive[0]:
                self._game_over = True
                self._winner = -1
                return
        else:
            if not any(alive):
                self._game_over = True; self._winner = -1; return
            if not alive[0]:
                self._game_over = True; self._winner = 1; return
            if not alive[1]:
                self._game_over = True; self._winner = 0; return

        for p in range(np_):
            nh = new_heads[p]
            self._snakes[p].appendleft(nh)
            if nh == self._food:
                self._scores[p] += 1
                self._score_flash = 0.35
                self._pulses[p].append(0.0)
                self._step_interval = max(
                    self._MIN_INTERVAL,
                    self._step_interval - self._SPEED_DECAY,
                )
                self._place_food()
            else:
                self._snakes[p].pop()

    # ── Wall animation ────────────────────────────────────────────────────────
    def _draw_walls(self, frame: np.ndarray) -> None:
        if self._difficulty == 0:
            return
        # Hard = amber, Very Hard = red
        wr, wg, wb = (210, 160, 0) if self._difficulty == 1 else (200, 30, 30)
        t = self._wall_time
        # Wave travels along wall: period ~16px, speed ~24px/s
        def wall_px(pos: int):
            b = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(pos * 0.40 - t * 4.5))
            return (int(wr * b), int(wg * b), int(wb * b))

        wall_tb   = True
        wall_side = self._difficulty >= 2

        if wall_tb:
            for x in range(64):
                c = wall_px(x)
                frame[0, x] = c; frame[1, x] = c
                frame[62, x] = c; frame[63, x] = c
        if wall_side:
            for y in range(64):
                c = wall_px(y)
                frame[y, 0] = c; frame[y, 1] = c
                frame[y, 62] = c; frame[y, 63] = c

    # ── Draw ──────────────────────────────────────────────────────────────────
    def _draw(self) -> np.ndarray:
        frame = np.zeros((64, 64, 3), dtype=np.uint8)

        # ── Waiting / title screen ─────────────────────────────────────────
        if self._waiting:
            # Yellow border (2px)
            frame[0:2,  :] = (200, 170, 0)
            frame[62:64, :] = (200, 170, 0)
            frame[:, 0:2]  = (200, 170, 0)
            frame[:, 62:64] = (200, 170, 0)
            # Original colours: green snake name, grey prompt
            _draw_centered(frame, 16, "SNAKE", (0, 210, 60), scale=2)
            _draw_centered(frame, 43, "PRESS", (130, 130, 130))
            _draw_centered(frame, 51, "START", (180, 180, 180))
            return frame

        # ── Game over screen (clean — no snake/food) ───────────────────────
        if self._game_over:
            # Pure black background
            # Thin red border (2px)
            frame[0:2,  :] = (160, 0, 0)
            frame[62:64, :] = (160, 0, 0)
            frame[:, 0:2]  = (160, 0, 0)
            frame[:, 62:64] = (160, 0, 0)
            _draw_centered(frame, 6,  "GAME", (220, 20, 20), scale=2)
            _draw_centered(frame, 18, "OVER", (220, 20, 20), scale=2)
            # Divider
            frame[31, 8:56] = (80, 20, 20)
            if self._n_players == 1:
                _draw_centered(frame, 35, "SCORE", (130, 100, 100))
                _draw_centered(frame, 43, str(self._scores[0]), (255, 210, 0), scale=2)
            elif self._winner == -1:
                _draw_centered(frame, 40, "DRAW", (255, 210, 0), scale=2)
            else:
                _draw_centered(frame, 35, f"P{self._winner + 1}", (255, 210, 0), scale=2)
                _draw_centered(frame, 47, "WINS", (255, 210, 0), scale=2)
            # Restart hint — safely above the bottom border
            _draw_centered(frame, 56, "START", (70, 60, 60))
            return frame

        # ── Pause screen ───────────────────────────────────────────────────
        if self._paused:
            # Draw dimmed game underneath
            fx, fy = self._food
            frame[fy*CELL:(fy+1)*CELL, fx*CELL:(fx+1)*CELL] = (80, 20, 0)
            colors = [C_P1, C_P2]
            for p in range(self._n_players):
                snake = self._snakes[p]
                n = len(snake)
                cr, cg, cb = colors[p]
                for i, (sx, sy) in enumerate(snake):
                    t = i / max(n - 1, 1)
                    shade = max(0.10, (1.0 - t * 0.90) * 0.30)
                    frame[sy*CELL:(sy+1)*CELL, sx*CELL:(sx+1)*CELL] = (
                        int(cr*shade), int(cg*shade), int(cb*shade))
            # Pause overlay text
            _draw_centered(frame, 22, "GAME", (180, 180, 180), scale=2)
            _draw_centered(frame, 34, "PAUSED", (180, 180, 180))
            _draw_centered(frame, 46, "SELECT", (100, 100, 100))
            _draw_centered(frame, 53, "RESUME", (100, 100, 100))
            return frame

        # ── Gameplay ───────────────────────────────────────────────────────
        # Food (pulsing orange)
        fx, fy = self._food
        pulse = 0.72 + 0.28 * math.sin(self._food_pulse)
        fr, fg, fb = C_FOOD
        fc = (int(fr * pulse), int(fg * pulse), int(fb * pulse))
        frame[fy*CELL:(fy+1)*CELL, fx*CELL:(fx+1)*CELL] = fc
        # Glow around food
        glow_v = int(55 * pulse)
        for ddy, ddx in ((-1,0),(1,0),(0,-1),(0,1)):
            gy, gx = fy + ddy, fx + ddx
            if 0 <= gx < GW and 0 <= gy < GH:
                frame[gy*CELL:(gy+1)*CELL, gx*CELL:(gx+1)*CELL] = (
                    min(255, glow_v), 0, 0)

        # Snake bodies (gradient head→tail + feed pulse wave)
        colors = [C_P1, C_P2]
        _PULSE_R = 2.8   # radius in segments
        for p in range(self._n_players):
            snake = self._snakes[p]
            n = len(snake)
            cr, cg, cb = colors[p]
            pulses = self._pulses[p]
            for i, (sx, sy) in enumerate(snake):
                t = i / max(n - 1, 1)
                shade = max(0.28, 1.0 - t * 0.72)
                r = int(cr * shade)
                g = int(cg * shade)
                b = int(cb * shade)
                # Pulse: brightest at centre, fades to edge
                pk = 0.0
                for pos in pulses:
                    d = abs(i - pos)
                    if d < _PULSE_R:
                        pk = max(pk, 1.0 - d / _PULSE_R)
                if pk > 0:
                    # Warm orange/yellow wash riding along the body
                    r = min(255, r + int(pk * 210))
                    g = min(255, g + int(pk * 130))
                    b = min(255, b + int(pk *  20))
                frame[sy*CELL:(sy+1)*CELL, sx*CELL:(sx+1)*CELL] = (r, g, b)

        # Score HUD — position clears walls; flashes yellow on eat
        score_col = (255, 220, 0) if self._score_flash > 0 else (100, 100, 100)
        sx0 = 3 if self._difficulty >= 2 else 1   # left of score
        sy0 = 3 if self._difficulty >= 1 else 1   # top of score
        if self._n_players == 1:
            _draw_text(frame, sx0, sy0, str(self._scores[0]), score_col)
        else:
            p1s = str(self._scores[0])
            p2s = str(self._scores[1])
            rx = 63 - _text_width(p2s) - (2 if self._difficulty >= 2 else 0)
            _draw_text(frame, sx0, sy0, p1s, score_col)
            _draw_text(frame, rx,  sy0, p2s, score_col)

        # Draw walls on top of everything
        self._draw_walls(frame)
        return frame

    # ── Tick ──────────────────────────────────────────────────────────────────
    def tick(self, dt: float) -> np.ndarray:
        self._food_pulse += dt * 4.0
        self._wall_time  += dt

        if self._waiting or self._game_over or self._paused:
            return self._draw()

        self._score_flash = max(0.0, self._score_flash - dt)
        # Advance feed pulses (~20 segments/sec)
        for p in range(self._n_players):
            n = len(self._snakes[p])
            self._pulses[p] = [
                pos + 20.0 * dt
                for pos in self._pulses[p]
                if pos < n + 3
            ]
        self._timer += dt
        while self._timer >= self._step_interval:
            self._timer -= self._step_interval
            self._step()
            if self._game_over:
                break

        return self._draw()

    # ── Input ─────────────────────────────────────────────────────────────────
    def handle_input(self, player: int, action: str) -> None:
        if action == "start":
            if self._game_over or self._waiting:
                self._reset()
                self._waiting = False
            else:
                self._paused = not self._paused
            return

        if action == "select":
            if not self._waiting and not self._game_over:
                self._paused = not self._paused
            return

        if self._waiting:
            # Any direction starts the game for single-player
            if action in DIRS and self._n_players == 1:
                self._waiting = False

        new_dir = DIRS.get(action)
        if new_dir is None:
            return

        # In 1-player mode, both P1 and P2 input control P1
        target = 0 if self._n_players == 1 else player
        if target not in (0, 1):
            return

        cur = self._dirs[target]
        if new_dir[0] != -cur[0] or new_dir[1] != -cur[1]:
            self._queued[target] = new_dir

    def is_over(self) -> bool:
        return self._game_over

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings(self) -> list[dict]:
        return [
            {"key": "players", "label": "Players", "type": "select",
             "options": [{"value": 1, "label": "1 Player"},
                         {"value": 2, "label": "2 Players"}],
             "value": self._n_players},
            {"key": "difficulty", "label": "Difficulty", "type": "select",
             "options": [{"value": 0, "label": "Normal"},
                         {"value": 1, "label": "Hard"},
                         {"value": 2, "label": "Very Hard"}],
             "value": self._difficulty},
        ]

    def apply_setting(self, key: str, value) -> None:
        if key == "players":
            n = max(1, min(2, int(value)))
            if n != self._n_players:
                self._n_players = n
                self._reset()
        elif key == "difficulty":
            d = max(0, min(2, int(value)))
            if d != self._difficulty:
                self._difficulty = d
                self._reset()
