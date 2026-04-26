from .config import RIGHT, PAC_START, get_speeds
from .maze import is_passable, MAZE_W, TUNNEL_ROW


class PacMan:
    def __init__(self, level: int = 1):
        self.pos_x      = float(PAC_START[0])
        self.pos_y      = float(PAC_START[1])
        self.direction  = RIGHT
        self._next_dir  = None
        self._moving    = False
        self._spd       = get_speeds(level)
        self.eating_dot = False
        self.mouth_open = True
        self._mouth_tick = 0

    def set_direction(self, d: tuple) -> None:
        self._next_dir = d

    def update(self, maze, level: int) -> None:
        self._spd = get_speeds(level)
        spd = self._spd[1] if self.eating_dot else self._spd[0]
        self.eating_dot = False

        tx = round(self.pos_x)
        ty = round(self.pos_y)
        at_center = abs(self.pos_x - tx) + abs(self.pos_y - ty) < 0.5

        # Apply queued direction at tile centre if that path is open
        if self._next_dir is not None and at_center:
            ndx, ndy = self._next_dir
            if is_passable(maze, tx + ndx, ty + ndy, ghost_mode="pacman"):
                self.direction = self._next_dir
                self._next_dir = None
                self._moving = True
                self.pos_x = float(tx)
                self.pos_y = float(ty)

        if self._moving:
            dx, dy = self.direction
            nx = self.pos_x + dx * spd
            ny = self.pos_y + dy * spd
            ntx = round(nx) if dx != 0 else tx
            nty = round(ny) if dy != 0 else ty
            if is_passable(maze, ntx, nty, ghost_mode="pacman"):
                self.pos_x = nx
                self.pos_y = ny
            else:
                # Hit a wall — snap to tile centre and stop until next input
                self.pos_x = float(tx)
                self.pos_y = float(ty)
                self._moving = False

        # Tunnel wrap
        if abs(self.pos_y - TUNNEL_ROW) < 0.6:
            if self.pos_x < 0:
                self.pos_x = float(MAZE_W - 1)
            elif self.pos_x >= MAZE_W:
                self.pos_x = 0.0

        self._mouth_tick = (self._mouth_tick + 1) % 8
        self.mouth_open  = self._mouth_tick < 4
