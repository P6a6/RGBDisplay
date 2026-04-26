import math
import random
from .config import (
    UP, DOWN, LEFT, RIGHT, OPPOSITE, ALL_DIRS,
    SCATTER_TARGETS, NO_UP_TILES, HOUSE_ENTRY,
    HOUSE_Y_MIN, HOUSE_Y_MAX, get_speeds,
)
from .maze import is_passable, MAZE_W, TUNNEL_ROW

MODE_SCATTER    = "scatter"
MODE_CHASE      = "chase"
MODE_FRIGHTENED = "frightened"
MODE_EATEN      = "eaten"
MODE_HOUSE      = "house"


def _choose_direction(col: int, row: int, current_dir: tuple,
                      target: tuple, maze, is_frightened: bool) -> tuple:
    """
    Pick exit direction when entering tile (col, row).
    Rules:
     - Cannot reverse (no opposite of current_dir)
     - Cannot choose UP at NO_UP_TILES intersections
     - Frightened: random valid direction
     - Otherwise: direction minimising Euclidean² distance to target
     - Tie-break: UP > LEFT > DOWN > RIGHT (ALL_DIRS order)
    """
    forbidden = OPPOSITE[current_dir]
    ghost_passable = "normal"  # ghosts use normal passability at junctions

    candidates = []
    for d in ALL_DIRS:
        if d == forbidden:
            continue
        if d == UP and (col, row) in NO_UP_TILES:
            continue
        nx, ny = col + d[0], row + d[1]
        if not is_passable(maze, nx, ny, ghost_mode="normal"):
            continue
        candidates.append(d)

    if not candidates:
        # Dead end — allow reversal
        rev = OPPOSITE[current_dir]
        nx, ny = col + rev[0], row + rev[1]
        if is_passable(maze, nx, ny, ghost_mode="normal"):
            return rev
        return current_dir

    if is_frightened:
        return random.choice(candidates)

    tx, ty = target
    best, best_d2 = candidates[0], float('inf')
    for d in candidates:
        nx, ny = col + d[0], row + d[1]
        d2 = (nx - tx) ** 2 + (ny - ty) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = d
    return best


class Ghost:
    def __init__(self, name: str, tile: tuple, outside: bool,
                 dot_limit: int, level: int):
        self.name        = name
        self.tile_x      = tile[0]
        self.tile_y      = tile[1]
        self.pos_x       = float(tile[0])
        self.pos_y       = float(tile[1])
        self.direction   = LEFT if outside else UP
        self.mode        = MODE_SCATTER if outside else MODE_HOUSE
        self.dot_limit   = dot_limit  # personal counter limit to exit house
        self.dot_counter = 0          # personal dots eaten while in house

        self._last_tile  = tile       # for tile-crossing detection
        self._level      = level
        self._spd        = get_speeds(level)

        self.flash       = False      # frightened flash state for drawing

    # ── Movement ──────────────────────────────────────────────────────────────
    def update(self, maze, pacman, blinky, global_mode: str) -> None:
        if self.mode == MODE_HOUSE:
            self._bounce_in_house()
            return

        # Eaten ghosts pass through door
        g_mode = "eaten" if self.mode == MODE_EATEN else "normal"

        spd = self._get_speed(maze)
        self.pos_x += self.direction[0] * spd
        self.pos_y += self.direction[1] * spd

        # Tunnel wrap on row 14
        if abs(self.pos_y - TUNNEL_ROW) < 0.6:
            if self.pos_x < 0:
                self.pos_x = float(MAZE_W - 1)
            elif self.pos_x >= MAZE_W:
                self.pos_x = 0.0

        cur_tile = (round(self.pos_x), round(self.pos_y))
        if cur_tile != self._last_tile:
            # Snap to tile centre
            self.pos_x = float(cur_tile[0])
            self.pos_y = float(cur_tile[1])

            col, row = cur_tile

            # Eaten ghost arriving at house entry → re-enter house
            if self.mode == MODE_EATEN and cur_tile == HOUSE_ENTRY:
                self.mode  = MODE_HOUSE
                self.direction = DOWN
                self._last_tile = cur_tile
                return

            # Choose next direction from this tile
            target = self._get_target(pacman, blinky, global_mode)
            self.direction = _choose_direction(
                col, row, self.direction, target, maze,
                is_frightened=(self.mode == MODE_FRIGHTENED),
            )
            self._last_tile = cur_tile

    def _get_speed(self, maze) -> float:
        spd = self._spd
        col, row = round(self.pos_x), round(self.pos_y)
        if self.mode == MODE_FRIGHTENED:
            return spd[4]
        if self.mode == MODE_EATEN:
            return spd[5]
        # Tunnel slow-down
        if row == TUNNEL_ROW and (col <= 5 or col >= 22):
            return spd[3]
        return spd[2]

    def _get_target(self, pacman, blinky, global_mode: str) -> tuple:
        if self.mode == MODE_EATEN:
            return HOUSE_ENTRY

        # In scatter phase or when the global mode is scatter
        if global_mode == MODE_SCATTER and self.mode != MODE_FRIGHTENED:
            return SCATTER_TARGETS[self.name]

        px = round(pacman.pos_x)
        py = round(pacman.pos_y)
        dx, dy = pacman.direction

        if self.name == "blinky":
            return (px, py)

        elif self.name == "pinky":
            tx, ty = px + dx * 4, py + dy * 4
            if pacman.direction == UP:
                tx -= 4   # original up-overflow bug, preserved
            return (tx, ty)

        elif self.name == "inky":
            rx = px + dx * 2
            ry = py + dy * 2
            if pacman.direction == UP:
                rx -= 2
            bx = round(blinky.pos_x)
            by = round(blinky.pos_y)
            return (rx + (rx - bx), ry + (ry - by))

        elif self.name == "clyde":
            dist = math.sqrt((self.pos_x - px) ** 2 + (self.pos_y - py) ** 2)
            if dist > 8:
                return (px, py)
            else:
                return SCATTER_TARGETS["clyde"]

        return (px, py)

    def _bounce_in_house(self) -> None:
        speed = 0.04
        self.pos_y += self.direction[1] * speed
        if self.pos_y <= HOUSE_Y_MIN:
            self.pos_y = HOUSE_Y_MIN
            self.direction = DOWN
        elif self.pos_y >= HOUSE_Y_MAX:
            self.pos_y = HOUSE_Y_MAX
            self.direction = UP
        self._last_tile = (round(self.pos_x), round(self.pos_y))

    # ── House exit ────────────────────────────────────────────────────────────
    def release_from_house(self, maze) -> None:
        """Move ghost out of the house to the junction above."""
        self.mode    = MODE_SCATTER
        self.pos_x   = 13.0
        self.pos_y   = 11.0
        self.direction = LEFT
        self._last_tile = (13, 11)

    # ── Collision ─────────────────────────────────────────────────────────────
    def check_collision(self, pacman) -> str:
        px, py = round(pacman.pos_x), round(pacman.pos_y)
        gx, gy = round(self.pos_x),  round(self.pos_y)
        if (px, py) == (gx, gy):
            if self.mode == MODE_FRIGHTENED:
                return "eaten"
            if self.mode in (MODE_SCATTER, MODE_CHASE):
                return "kill"
        return "none"

    # ── Mode switch ───────────────────────────────────────────────────────────
    def set_global_mode(self, mode: str) -> None:
        if self.mode in (MODE_SCATTER, MODE_CHASE):
            self.direction = OPPOSITE[self.direction]
            self.mode = MODE_CHASE if mode == "chase" else MODE_SCATTER

    def frighten(self) -> None:
        if self.mode in (MODE_SCATTER, MODE_CHASE):
            self.direction = OPPOSITE[self.direction]
            self.mode = MODE_FRIGHTENED

    def unfrighten(self) -> None:
        if self.mode == MODE_FRIGHTENED:
            self.mode = MODE_CHASE

    def update_level(self, level: int) -> None:
        self._level = level
        self._spd   = get_speeds(level)
