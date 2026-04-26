import numpy as np
from .config import (
    CELL, OX, OY, MAZE_W, MAZE_H,
    C_WALL, C_DOT, C_PELLET, C_DOOR, C_PAC,
    C_BLINKY, C_PINKY, C_INKY, C_CLYDE,
    C_FRIGHT, C_FRIGHT_FLASH, C_EYES,
    FRIGHT_FLASH_THRESHOLD, FONT,
)
from .maze import WALL, DOT, PELLET, EMPTY, DOOR
from .ghost import MODE_FRIGHTENED, MODE_EATEN, MODE_HOUSE

_GHOST_COLS = {
    "blinky": C_BLINKY,
    "pinky":  C_PINKY,
    "inky":   C_INKY,
    "clyde":  C_CLYDE,
}


def _tp(tx: int, ty: int) -> tuple[int, int]:
    """Tile → top-left pixel."""
    return (OX + tx * CELL, OY + ty * CELL)


def _tw(text: str) -> int:
    return sum(len(FONT.get(c.upper(), FONT[' '])) + 1 for c in text) - 1


def _draw_text(frame: np.ndarray, x: int, y: int, text: str,
               color: tuple, scale: int = 1) -> None:
    cx = x
    for ch in text:
        cols = FONT.get(ch.upper(), FONT[' '])
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


def _draw_centered(frame: np.ndarray, y: int, text: str,
                   color: tuple, scale: int = 1) -> None:
    w = _tw(text) * scale
    _draw_text(frame, (64 - w) // 2, y, text, color, scale)


def draw_frame(frame: np.ndarray, gs) -> None:
    """Render entire game state into a (64,64,3) numpy frame."""

    # ── Maze ──────────────────────────────────────────────────────────────────
    for row in range(MAZE_H):
        for col in range(MAZE_W):
            cell = gs.maze[row][col]
            px, py = _tp(col, row)
            if px + CELL > 64 or py + CELL > 64:
                continue
            if cell == WALL:
                frame[py:py+CELL, px:px+CELL] = C_WALL
            elif cell == DOT:
                # Single pixel centred in the tile
                cx, cy = px + CELL // 2, py + CELL // 2
                if 0 <= cx < 64 and 0 <= cy < 64:
                    frame[cy, cx] = C_DOT
            elif cell == PELLET:
                if gs.tick_count % 30 < 20:   # blink
                    frame[py:py+CELL, px:px+CELL] = C_PELLET
            elif cell == DOOR:
                frame[py:py+1, px:px+CELL] = C_DOOR

    # ── Fruit ─────────────────────────────────────────────────────────────────
    if gs.fruit_visible:
        from .config import FRUIT_TILE
        fpx, fpy = _tp(*FRUIT_TILE)
        if 0 <= fpx < 63 and 0 <= fpy < 63:
            frame[fpy:fpy+CELL, fpx:fpx+CELL] = (255, 0, 100)   # magenta cherry

    # ── Ghosts ────────────────────────────────────────────────────────────────
    for ghost in gs.ghosts:
        if ghost.mode == MODE_HOUSE and not gs.show_ghost_in_house(ghost):
            # Draw ghost faintly in house
            pass
        gx, gy = _tp(round(ghost.pos_x), round(ghost.pos_y))
        if not (0 <= gx < 63 and 0 <= gy < 63):
            continue

        if ghost.mode == MODE_FRIGHTENED:
            remaining = gs.frightened_timer
            if remaining < FRIGHT_FLASH_THRESHOLD:
                flash_on = (gs.tick_count // 6) % 2 == 0
                col = C_FRIGHT_FLASH if flash_on else C_FRIGHT
            else:
                col = C_FRIGHT
            frame[gy:gy+CELL, gx:gx+CELL] = col
            # No eyes when frightened (blue blob)

        elif ghost.mode == MODE_EATEN:
            # Eyes only — draw two white pixels
            frame[gy,   gx  ] = C_EYES
            frame[gy,   gx+1] = C_EYES

        else:
            col = _GHOST_COLS.get(ghost.name, (255, 255, 255))
            frame[gy:gy+CELL, gx:gx+CELL] = col
            # Eyes: two white pixels on top row
            frame[gy, gx  ] = C_EYES
            frame[gy, gx+1] = C_EYES

    # ── Pac-Man ───────────────────────────────────────────────────────────────
    pac = gs.pacman
    ppx, ppy = _tp(round(pac.pos_x), round(pac.pos_y))
    if 0 <= ppx < 63 and 0 <= ppy < 63:
        frame[ppy:ppy+CELL, ppx:ppx+CELL] = C_PAC
        if pac.mouth_open:
            dx, dy = pac.direction
            if dx == 1:    # right → mouth on right column
                frame[ppy,   ppx+1] = 0
                frame[ppy+1, ppx+1] = 0
            elif dx == -1: # left
                frame[ppy,   ppx  ] = 0
                frame[ppy+1, ppx  ] = 0
            elif dy == -1: # up
                frame[ppy,   ppx  ] = 0
                frame[ppy,   ppx+1] = 0
            elif dy == 1:  # down
                frame[ppy+1, ppx  ] = 0
                frame[ppy+1, ppx+1] = 0

    # ── HUD ───────────────────────────────────────────────────────────────────
    # Lives as tiny yellow squares in the bottom-left border strip
    for i in range(gs.lives - 1):   # show remaining extra lives
        lx = OX + i * (CELL + 2)
        if lx + CELL <= 64:
            frame[62:64, lx:lx+CELL] = C_PAC

    # Level indicator — small dots on the right side of bottom strip
    for i in range(min(gs.level, 7)):
        lx = 63 - i * (CELL + 1)
        if lx >= 0:
            frame[62:64, lx:lx+1] = (255, 100, 0)

    # Score — top strip (2 pixel rows above maze)
    score_str = str(gs.score)
    sw = _tw(score_str)
    if OY >= 6:
        _draw_text(frame, (64 - sw) // 2, 0, score_str, (255, 255, 255))
    else:
        # No space above maze — draw in top-left of frame, may overlap maze slightly
        _draw_text(frame, 1, 0, score_str, (200, 200, 200))


def draw_title(frame: np.ndarray) -> None:
    frame[0:2,   :] = (33, 33, 200)
    frame[62:64, :] = (33, 33, 200)
    frame[:, 0:2]   = (33, 33, 200)
    frame[:, 62:64] = (33, 33, 200)
    _draw_centered(frame, 10, "PAC",  (255, 255,   0), scale=2)
    _draw_centered(frame, 22, "MAN",  (255, 255,   0), scale=2)
    _draw_centered(frame, 38, "PRESS", (150, 150, 150))
    _draw_centered(frame, 46, "START", (200, 200, 200))


def draw_game_over(frame: np.ndarray, score: int) -> None:
    frame[0:2,   :] = (160, 0, 0)
    frame[62:64, :] = (160, 0, 0)
    frame[:, 0:2]   = (160, 0, 0)
    frame[:, 62:64] = (160, 0, 0)
    _draw_centered(frame,  6, "GAME", (220, 20, 20), scale=2)
    _draw_centered(frame, 18, "OVER", (220, 20, 20), scale=2)
    frame[31, 8:56] = (80, 20, 20)
    _draw_centered(frame, 34, "SCORE", (130, 100, 100))
    sc = str(score)
    scw = _tw(sc) * 2
    _draw_centered(frame, 41 if scw <= 56 else 44, sc,
                   (255, 210, 0), scale=2 if scw <= 56 else 1)
    _draw_centered(frame, 56, "START", (70, 60, 60))


def draw_level_clear(frame: np.ndarray, level: int) -> None:
    frame[0:2,   :] = (0, 160, 0)
    frame[62:64, :] = (0, 160, 0)
    frame[:, 0:2]   = (0, 160, 0)
    frame[:, 62:64] = (0, 160, 0)
    _draw_centered(frame, 10, "LEVEL", (0, 220, 80), scale=2)
    _draw_centered(frame, 34, str(level), (255, 255, 0), scale=2)
    _draw_centered(frame, 50, "CLEAR",  (0, 180, 60), scale=2)


def draw_dying(frame: np.ndarray, pac, t: float, total: float = 1.5) -> None:
    """Death animation: flash then expanding burst."""
    ppx, ppy = _tp(round(pac.pos_x), round(pac.pos_y))
    cx, cy = ppx + 1, ppy + 1
    if t > total * 0.35:
        if int(t * 10) % 2 == 0 and 0 <= ppx < 63 and 0 <= ppy < 63:
            frame[ppy:ppy+CELL, ppx:ppx+CELL] = C_PAC
    else:
        progress = 1.0 - (t / (total * 0.35))
        r = int(progress * 7) + 1
        for d in range(1, r + 1):
            for px, py in [(cx+d, cy), (cx-d, cy), (cx, cy+d), (cx, cy-d),
                           (cx+d, cy+d), (cx-d, cy-d), (cx+d, cy-d), (cx-d, cy+d)]:
                if 0 <= px < 64 and 0 <= py < 64:
                    fade = max(0, 255 - d * 35)
                    frame[py, px] = (fade, fade, 0)


def draw_paused(frame: np.ndarray) -> None:
    frame[:] = (frame * 0.3).astype(np.uint8)
    _draw_centered(frame, 22, "PAUSED", (180, 180, 180))
    _draw_centered(frame, 34, "SELECT", (100, 100, 100))
    _draw_centered(frame, 41, "RESUME", (100, 100, 100))
