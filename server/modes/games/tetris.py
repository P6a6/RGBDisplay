import random
import numpy as np
from base_mode import BaseMode

# ── Layout ────────────────────────────────────────────────────────────────────
BOARD_W = 12
BOARD_H = 20
CELL    = 3          # px per cell: 2px colour + 1px gap
BX      = 2          # board pixel origin x
BY      = 2          # board pixel origin y
IX      = 40         # info panel left edge  (12*3 + 2 + 2 = 40)

# ── Pieces ────────────────────────────────────────────────────────────────────
_NAMES = ('I', 'O', 'T', 'S', 'Z', 'J', 'L')

_SPAWN = {
    'I': [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]],
    'O': [[0,1,1,0],[0,1,1,0],[0,0,0,0],[0,0,0,0]],
    'T': [[0,1,0,0],[1,1,1,0],[0,0,0,0],[0,0,0,0]],
    'S': [[0,1,1,0],[1,1,0,0],[0,0,0,0],[0,0,0,0]],
    'Z': [[1,1,0,0],[0,1,1,0],[0,0,0,0],[0,0,0,0]],
    'J': [[1,0,0,0],[1,1,1,0],[0,0,0,0],[0,0,0,0]],
    'L': [[0,0,1,0],[1,1,1,0],[0,0,0,0],[0,0,0,0]],
}

def _all_rots(m_list):
    m = np.array(m_list, dtype=bool)
    return [np.rot90(m, k=(4 - i) % 4) for i in range(4)]

_ROTS = {n: _all_rots(_SPAWN[n]) for n in _NAMES}

_COLORS = [
    (0,   0,   0  ),  # 0 empty
    (0,   210, 225),  # 1 I  cyan
    (225, 200, 0  ),  # 2 O  yellow
    (155, 0,   215),  # 3 T  purple
    (0,   200, 40 ),  # 4 S  green
    (225, 25,  25 ),  # 5 Z  red
    (35,  80,  225),  # 6 J  blue
    (225, 115, 0  ),  # 7 L  orange
]
_CIDX = {n: i + 1 for i, n in enumerate(_NAMES)}

# ── Scoring ───────────────────────────────────────────────────────────────────
_LINE_PTS = (0, 100, 300, 500, 800)

def _drop_interval(level: int, hard: bool = False) -> float:
    base = max(0.05, 0.80 - (level - 1) * 0.07)
    return base * (0.85 if hard else 1.0)

# ── Font & text helpers ───────────────────────────────────────────────────────
# column-based bitmasks: bit4=top pixel, bit0=bottom pixel
_FONT: dict[str, list[int]] = {
    ' ': [0, 0, 0],
    'A': [15, 20, 15], 'B': [31, 21, 10], 'C': [14, 17, 17],
    'D': [31, 17, 14], 'E': [31, 21, 17], 'F': [31, 20, 16],
    'G': [14, 21, 23], 'H': [31, 4,  31], 'I': [17, 31, 17],
    'J': [2,  17, 30], 'K': [31, 4,  27], 'L': [31, 1,  1 ],
    'M': [31, 24, 4, 24, 31], 'N': [31, 8, 4, 31],
    'O': [14, 17, 14], 'P': [31, 20, 24], 'Q': [14, 17, 15],
    'R': [31, 20, 11], 'S': [9,  21, 18], 'T': [16, 31, 16],
    'U': [30, 1,  30], 'V': [28, 3,  28], 'W': [31, 2, 4, 2, 31],
    'X': [27, 4,  27], 'Y': [24, 7,  24], 'Z': [19, 21, 9 ],
    '0': [14, 17, 14], '1': [9,  31, 1 ], '2': [23, 21, 29],
    '3': [21, 21, 31], '4': [28, 4,  31], '5': [29, 21, 23],
    '6': [31, 21, 7 ], '7': [16, 19, 28], '8': [10, 21, 10],
    '9': [12, 21, 14], '-': [4, 4, 4],
}

def _text_width(text: str) -> int:
    return sum(len(_FONT.get(c.upper(), _FONT[' '])) + 1 for c in text) - 1

def _draw_text(frame, x: int, y: int, text: str, color, scale: int = 1):
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
                            if 0 <= px < 64 and 0 <= py < 64:
                                frame[py, px] = color
        cx += (len(cols) + 1) * scale

def _draw_centered(frame, y: int, text: str, color, scale: int = 1):
    w = _text_width(text) * scale
    _draw_text(frame, (64 - w) // 2, y, text, color, scale)

INFO_W = 64 - IX  # width of info panel in pixels

def _info_txt(frame, y: int, text: str, color, scale: int = 1):
    w = _text_width(text) * scale
    _draw_text(frame, IX + (INFO_W - w) // 2, y, text, color, scale)


# ── Mode ──────────────────────────────────────────────────────────────────────
class Tetris(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name":        "Tetris",
            "description": "Classic falling blocks — clear lines to score",
            "category":    "games",
        }

    def __init__(self):
        self._difficulty = 0  # 0=Easy, 1=Hard
        self._reset()

    # ── State init ────────────────────────────────────────────────────────────
    def _reset(self) -> None:
        self._board       = np.zeros((BOARD_H, BOARD_W), dtype=np.uint8)
        self._score       = 0
        self._lines       = 0
        self._level       = 1
        self._bag: list   = []
        self._next        = self._from_bag()
        self._piece: dict = {}
        self._drop_timer  = 0.0
        self._clear_timer = 0.0
        self._clearing: list[int] = []
        self._lock_flash: set     = set()
        self._lock_timer  = 0.0
        self._game_over   = False
        self._waiting     = True
        self._paused      = False
        self._spawn()

    def _from_bag(self) -> str:
        if not self._bag:
            self._bag = list(_NAMES)
            random.shuffle(self._bag)
        return self._bag.pop()

    def _spawn(self) -> None:
        name = self._next
        self._next  = self._from_bag()
        self._piece = {'name': name, 'rot': 0,
                       'x': (BOARD_W - 4) // 2, 'y': -1}
        if not self._fits(_ROTS[name][0], self._piece['x'], self._piece['y']):
            self._game_over = True

    # ── Physics ───────────────────────────────────────────────────────────────
    def _fits(self, mask, px: int, py: int) -> bool:
        for r in range(4):
            for c in range(4):
                if not mask[r, c]:
                    continue
                bx, by = px + c, py + r
                if bx < 0 or bx >= BOARD_W or by >= BOARD_H:
                    return False
                if by >= 0 and self._board[by, bx]:
                    return False
        return True

    def _ghost(self) -> int:
        p  = self._piece
        m  = _ROTS[p['name']][p['rot']]
        gy = p['y']
        while self._fits(m, p['x'], gy + 1):
            gy += 1
        return gy

    def _lock(self) -> None:
        p  = self._piece
        m  = _ROTS[p['name']][p['rot']]
        ci = _CIDX[p['name']]
        locked: set = set()
        for r in range(4):
            for c in range(4):
                if m[r, c]:
                    bx, by = p['x'] + c, p['y'] + r
                    if 0 <= by < BOARD_H and 0 <= bx < BOARD_W:
                        self._board[by, bx] = ci
                        locked.add((bx, by))
        self._lock_flash = locked
        self._lock_timer = 0.10

        full = np.where(np.all(self._board > 0, axis=1))[0]
        if len(full):
            self._clearing    = list(full)
            self._clear_timer = 0.22
        else:
            self._spawn()

    def _do_clear(self) -> None:
        n    = len(self._clearing)
        keep = [r for r in range(BOARD_H) if r not in set(self._clearing)]
        new  = np.zeros_like(self._board)
        new[n:] = self._board[keep]
        self._board  = new
        self._lines += n
        self._score += _LINE_PTS[min(n, 4)] * self._level
        self._level  = self._lines // 10 + 1
        self._clearing = []
        self._spawn()

    def _rotate(self, direction: int) -> None:
        p       = self._piece
        new_rot = (p['rot'] + direction) % 4
        nm      = _ROTS[p['name']][new_rot]
        for dx in (0, -1, 1, -2, 2):
            if self._fits(nm, p['x'] + dx, p['y']):
                p['rot']  = new_rot
                p['x']   += dx
                return

    # ── BaseMode ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._reset()

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        if self._waiting or self._game_over or self._paused:
            return self._draw()

        # Line-clear animation
        if self._clear_timer > 0:
            self._clear_timer -= dt
            if self._clear_timer <= 0:
                self._do_clear()
            return self._draw()

        # Lock flash decay
        self._lock_timer = max(0.0, self._lock_timer - dt)
        if self._lock_timer == 0:
            self._lock_flash = set()

        # Gravity
        self._drop_timer += dt
        hard = self._difficulty == 1
        interval = _drop_interval(self._level, hard)
        while self._drop_timer >= interval:
            self._drop_timer -= interval
            p = self._piece
            if self._fits(_ROTS[p['name']][p['rot']], p['x'], p['y'] + 1):
                p['y'] += 1
            else:
                self._lock()
                self._drop_timer = 0.0
                break

        return self._draw()

    # ── Drawing ───────────────────────────────────────────────────────────────
    def _draw(self) -> np.ndarray:
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        if self._waiting:
            self._draw_title(frame);   return frame
        if self._game_over:
            self._draw_gameover(frame); return frame
        self._draw_board(frame)
        if not self._clearing:
            self._draw_active(frame)
        self._draw_info(frame)
        if self._paused:
            self._draw_pause(frame)
        return frame

    def _draw_board(self, frame: np.ndarray) -> None:
        # Border
        bc = (38, 38, 38)
        frame[BY-1, BX-1:BX+BOARD_W*CELL+1] = bc
        frame[BY+BOARD_H*CELL, BX-1:BX+BOARD_W*CELL+1] = bc
        frame[BY-1:BY+BOARD_H*CELL+1, BX-1] = bc
        frame[BY-1:BY+BOARD_H*CELL+1, BX+BOARD_W*CELL] = bc

        # Locked cells
        for row in range(BOARD_H):
            for col in range(BOARD_W):
                ci = self._board[row, col]
                if ci == 0:
                    continue
                c = _COLORS[ci]
                if (col, row) in self._lock_flash and self._lock_timer > 0:
                    t = self._lock_timer / 0.10
                    c = tuple(min(255, int(v + (255 - v) * t * 0.75)) for v in c)
                px = BX + col * CELL
                py = BY + row * CELL
                frame[py:py+2, px:px+2] = c

        # Line-clear flash
        if self._clearing:
            t  = max(0.0, self._clear_timer / 0.22)
            fl = int(240 * t)
            for row in self._clearing:
                for col in range(BOARD_W):
                    px = BX + col * CELL
                    py = BY + row * CELL
                    frame[py:py+2, px:px+2] = (fl, fl, fl)

    def _draw_active(self, frame: np.ndarray) -> None:
        p    = self._piece
        mask = _ROTS[p['name']][p['rot']]
        col  = _COLORS[_CIDX[p['name']]]
        hard = self._difficulty == 1

        # Ghost (dim outline) — Easy only
        if not hard:
            gy = self._ghost()
            if gy > p['y']:
                gc = tuple(max(0, int(v * 0.15)) for v in col)
                for r in range(4):
                    for c in range(4):
                        if mask[r, c]:
                            bc, br = p['x']+c, gy+r
                            if 0 <= br < BOARD_H and 0 <= bc < BOARD_W:
                                px = BX + bc * CELL
                                py = BY + br * CELL
                                frame[py:py+2, px:px+2] = gc

        # Active piece
        for r in range(4):
            for c in range(4):
                if mask[r, c]:
                    bc, br = p['x']+c, p['y']+r
                    if 0 <= br < BOARD_H and 0 <= bc < BOARD_W:
                        px = BX + bc * CELL
                        py = BY + br * CELL
                        frame[py:py+2, px:px+2] = col

    def _draw_info(self, frame: np.ndarray) -> None:
        hard = self._difficulty == 1

        # Thin separator line
        frame[BY:BY+BOARD_H*CELL, IX-1] = (22, 22, 22)

        # ── NEXT piece (Easy only) ─────────────────────────────────────────────
        if not hard:
            _draw_text(frame, IX + 2, 2, "NXT", (58, 58, 58))
            nm  = _ROTS[self._next][0]
            nc  = _COLORS[_CIDX[self._next]]
            ri_, ci_ = np.where(nm)
            if len(ri_):
                min_r, min_c = int(ri_.min()), int(ci_.min())
                max_r, max_c = int(ri_.max()), int(ci_.max())
                pw = (max_c - min_c + 1) * 2
                ph = (max_r - min_r + 1) * 2
                ox = IX + (INFO_W - pw) // 2
                oy = 9  + (10 - ph) // 2
                for r in range(4):
                    for c in range(4):
                        if nm[r, c]:
                            x = ox + (c - min_c) * 2
                            y = oy + (r - min_r) * 2
                            if 0 <= x < 64 and 0 <= y < 64:
                                frame[y:y+2, x:x+2] = nc

        # ── Score ─────────────────────────────────────────────────────────────
        _info_txt(frame, 23, "SCORE", (55, 55, 55))
        _info_txt(frame, 30, str(self._score), (220, 195, 0))

        # ── Level ─────────────────────────────────────────────────────────────
        _info_txt(frame, 41, "LEVEL", (55, 55, 55))
        lc  = str(self._level)
        lw  = _text_width(lc) * 2
        _draw_text(frame, IX + (INFO_W - lw) // 2, 47, lc, (200, 200, 200), scale=2)

    def _draw_title(self, frame: np.ndarray) -> None:
        frame[0:2,   :] = (60, 0, 160)
        frame[62:64, :] = (60, 0, 160)
        frame[:, 0:2]   = (60, 0, 160)
        frame[:, 62:64] = (60, 0, 160)
        _draw_centered(frame, 16, "TETRIS", (140, 60, 220), scale=2)
        _draw_centered(frame, 43, "PRESS",  (130, 130, 130))
        _draw_centered(frame, 51, "START",  (180, 180, 180))

    def _draw_gameover(self, frame: np.ndarray) -> None:
        frame[0:2,   :] = (160, 0, 0)
        frame[62:64, :] = (160, 0, 0)
        frame[:, 0:2]   = (160, 0, 0)
        frame[:, 62:64] = (160, 0, 0)
        _draw_centered(frame, 6,  "GAME", (220, 20, 20), scale=2)
        _draw_centered(frame, 18, "OVER", (220, 20, 20), scale=2)
        frame[31, 8:56] = (80, 20, 20)
        _draw_centered(frame, 34, "SCORE", (120, 90, 90))
        sc  = str(self._score)
        scw = _text_width(sc) * 2
        sy  = 41 if scw <= 56 else 44
        ssc = 2  if scw <= 56 else 1
        _draw_centered(frame, sy, sc, (255, 210, 0), scale=ssc)
        _draw_centered(frame, 56, "START", (65, 55, 55))

    def _draw_pause(self, frame: np.ndarray) -> None:
        frame[:] = (frame * 0.35).astype(np.uint8)
        _draw_centered(frame, 22, "PAUSED", (180, 180, 180))
        _draw_centered(frame, 34, "SELECT", (100, 100, 100))
        _draw_centered(frame, 41, "RESUME", (100, 100, 100))

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

        if self._waiting or self._game_over or self._paused or self._clear_timer > 0:
            return

        p    = self._piece
        mask = _ROTS[p['name']][p['rot']]

        if   action == "left":
            if self._fits(mask, p['x'] - 1, p['y']): p['x'] -= 1
        elif action == "right":
            if self._fits(mask, p['x'] + 1, p['y']): p['x'] += 1
        elif action == "down":
            if self._fits(mask, p['x'], p['y'] + 1):
                p['y'] += 1
                self._drop_timer = 0.0
        elif action == "up":
            p['y'] = self._ghost()
            self._lock()
            self._drop_timer = 0.0
        elif action in ("a", "x"):
            self._rotate(+1)
        elif action in ("b", "y"):
            self._rotate(-1)

    def is_over(self) -> bool:
        return self._game_over

    def get_settings(self) -> list[dict]:
        return [
            {
                "key":     "difficulty",
                "label":   "Difficulty",
                "type":    "select",
                "value":   self._difficulty,
                "options": [
                    {"value": 0, "label": "Easy (ghost + next piece)"},
                    {"value": 1, "label": "Hard (no ghost, faster)"},
                ],
            }
        ]

    def apply_setting(self, key: str, value) -> None:
        if key == "difficulty":
            self._difficulty = int(value)
