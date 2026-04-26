import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
from base_mode import BaseMode

from .config import (
    get_scatter_chase, get_fright_dur, get_dot_limit,
    GLOBAL_LIMITS, FORCE_RELEASE_TIMEOUT,
    SCORE_DOT, SCORE_PELLET, SCORE_GHOST, SCORE_LIFE,
    FRUIT_DOTS, FRUIT_VISIBLE, FRUIT_SCORES,
    GHOST_STARTS, PAC_START,
    UP, DOWN, LEFT, RIGHT, OPPOSITE,
)
from .maze import make_maze, count_dots, DOT, PELLET, EMPTY, MAZE_W, TUNNEL_ROW
from .ghost import Ghost, MODE_SCATTER, MODE_CHASE, MODE_FRIGHTENED, MODE_EATEN, MODE_HOUSE
from .pacman_entity import PacMan
from .renderer import (draw_frame, draw_title, draw_game_over,
                        draw_level_clear, draw_dying, draw_paused)

_DIR_MAP = {
    "up": UP, "down": DOWN, "left": LEFT, "right": RIGHT,
}


class PacManMode(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name":        "Pac-Man",
            "description": "Eat all dots, avoid ghosts — power pellets let you eat them!",
            "category":    "games",
        }

    def __init__(self):
        self._state = "title"   # title | playing | dying | level_clear | game_over | paused
        self._score = 0
        self._lives = 3
        self._level = 1
        self._high_score = 0
        self._extra_life_awarded = False
        self._tick_count = 0
        self._init_level()

    # ── Level / game init ──────────────────────────────────────────────────────
    def _init_level(self) -> None:
        self.maze        = make_maze()
        self._dots_total = count_dots(self.maze)
        self._dots_left  = self._dots_total

        self._pacman     = PacMan(self._level)

        # Ghost house exit: use personal counters at level start
        self._use_global_counter = False
        self._global_counter     = 0

        self._ghosts: list[Ghost] = []
        for name, cfg in GHOST_STARTS.items():
            g = Ghost(
                name      = name,
                tile      = cfg["tile"],
                outside   = cfg["outside"],
                dot_limit = get_dot_limit(name, self._level),
                level     = self._level,
            )
            self._ghosts.append(g)

        # Scatter/chase sequence
        self._sc_seq    = get_scatter_chase(self._level)
        self._sc_idx    = 0
        self._sc_timer  = 0.0
        self._sc_mode   = "scatter"   # current scatter/chase phase

        self._fright_timer  = 0.0
        self._ghost_combo   = 0       # consecutive ghost eats in one pellet

        self._force_timer   = 0.0    # force-release countdown

        self._fruit_visible = False
        self._fruit_timer   = 0.0
        self._fruit_spawned = [False, False]   # at 70 and 170 dots eaten
        self._dots_eaten    = 0

        self._state_timer   = 0.0
        self.tick_count     = 0      # exposed for renderer

    def _respawn_entities(self) -> None:
        """Reset pacman and ghosts to start positions after a death."""
        self._pacman = PacMan(self._level)
        for i, (name, cfg) in enumerate(GHOST_STARTS.items()):
            g = self._ghosts[i]
            g.pos_x      = float(cfg["tile"][0])
            g.pos_y      = float(cfg["tile"][1])
            g.tile_x     = cfg["tile"][0]
            g.tile_y     = cfg["tile"][1]
            g.direction  = LEFT if cfg["outside"] else UP
            g.mode       = MODE_SCATTER if cfg["outside"] else MODE_HOUSE
            g._last_tile = cfg["tile"]
            g.update_level(self._level)
        # Switch to global counter after a death
        self._use_global_counter = True
        self._global_counter     = 0
        self._fright_timer       = 0.0
        self._force_timer        = 0.0

    # ── BaseMode ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        self._score     = 0
        self._lives     = 3
        self._level     = 1
        self._extra_life_awarded = False
        self._state     = "title"
        self._init_level()

    def stop(self) -> None:
        pass

    # ── Main tick ─────────────────────────────────────────────────────────────
    def tick(self, dt: float) -> np.ndarray:
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        self.tick_count  += 1
        self._tick_count += 1

        if self._state == "title":
            draw_title(frame)
            return frame

        if self._state == "game_over":
            if self._score > self._high_score:
                self._high_score = self._score
            draw_game_over(frame, self._score)
            return frame

        if self._state == "level_clear":
            self._state_timer -= dt
            if self._state_timer <= 0:
                self._level += 1
                self._init_level()
                self._state = "playing"
            draw_level_clear(frame, self._level - 1)
            return frame

        if self._state == "dying":
            self._state_timer -= dt
            draw_frame(frame, self)
            draw_dying(frame, self._pacman, self._state_timer)
            if self._state_timer <= 0:
                self._lives -= 1
                if self._lives <= 0:
                    self._state = "game_over"
                else:
                    self._respawn_entities()
                    self._state = "playing"
            return frame

        if self._state == "paused":
            draw_frame(frame, self)
            draw_paused(frame)
            return frame

        # ── Playing ───────────────────────────────────────────────────────────
        self._update(dt)
        draw_frame(frame, self)
        return frame

    # ── Game update ───────────────────────────────────────────────────────────
    def _update(self, dt: float) -> None:
        # 1. Scatter/chase phase timer
        self._update_sc_timer(dt)

        # 2. Frightened timer
        if self._fright_timer > 0:
            self._fright_timer -= dt
            if self._fright_timer <= 0:
                self._fright_timer = 0.0
                for g in self._ghosts:
                    g.unfrighten()

        # 3. Fruit
        self._update_fruit(dt)

        # 4. Force-release timer
        self._force_timer += dt
        if self._force_timer >= FORCE_RELEASE_TIMEOUT:
            self._force_timer = 0.0
            self._force_release()

        # 5. Ghost house exits (dot-counter based)
        self._check_ghost_exits()

        # 6. Move Pac-Man
        self._pacman.update(self.maze, self._level)

        # 7. Eat dot/pellet
        self._check_eat()

        # 8. Move ghosts
        blinky = self._ghosts[0]
        for g in self._ghosts:
            g.update(self.maze, self._pacman, blinky, self._sc_mode)

        # 9. Collision
        self._check_collisions()

        # 10. Level clear
        if self._dots_left == 0:
            self._state       = "level_clear"
            self._state_timer = 2.5

    # ── Scatter/chase ─────────────────────────────────────────────────────────
    def _update_sc_timer(self, dt: float) -> None:
        if self._sc_mode == "frightened":
            return
        self._sc_timer += dt
        if self._sc_idx >= len(self._sc_seq):
            return
        phase_mode, phase_dur = self._sc_seq[self._sc_idx]
        if phase_dur != float('inf') and self._sc_timer >= phase_dur:
            self._sc_timer = 0.0
            self._sc_idx  += 1
            if self._sc_idx < len(self._sc_seq):
                new_mode = self._sc_seq[self._sc_idx][0]
                self._switch_sc_mode(new_mode)

    def _switch_sc_mode(self, new_mode: str) -> None:
        old = self._sc_mode
        self._sc_mode = new_mode
        if old != new_mode:
            for g in self._ghosts:
                g.set_global_mode(new_mode)

    # ── Dot eating & pellets ──────────────────────────────────────────────────
    def _check_eat(self) -> None:
        tx = round(self._pacman.pos_x)
        ty = round(self._pacman.pos_y)
        if tx < 0 or tx >= 28 or ty < 0 or ty >= 31:
            return
        cell = self.maze[ty][tx]
        if cell == DOT:
            self.maze[ty][tx] = EMPTY
            self._score += SCORE_DOT
            self._dots_left  -= 1
            self._dots_eaten += 1
            self._pacman.eating_dot = True
            self._force_timer = 0.0
            self._on_dot_eaten()
            self._check_extra_life()

        elif cell == PELLET:
            self.maze[ty][tx] = EMPTY
            self._score += SCORE_PELLET
            self._dots_left  -= 1
            self._dots_eaten += 1
            self._force_timer = 0.0
            self._ghost_combo   = 0
            dur = get_fright_dur(self._level)
            self._fright_timer  = dur
            if dur > 0:
                for g in self._ghosts:
                    g.frighten()
            self._on_dot_eaten()
            self._check_extra_life()

        # Fruit
        if self._fruit_visible:
            from .config import FRUIT_TILE
            if (tx, ty) == FRUIT_TILE:
                pts = FRUIT_SCORES.get(self._level, 100)
                self._score += pts
                self._fruit_visible = False
                self._fruit_timer   = 0.0

    def _on_dot_eaten(self) -> None:
        ate = self._dots_eaten
        # Fruit spawn triggers
        for i, threshold in enumerate(FRUIT_DOTS):
            if ate == threshold and not self._fruit_spawned[i]:
                self._fruit_spawned[i] = True
                self._fruit_visible    = True
                self._fruit_timer      = FRUIT_VISIBLE

        # Global counter (after death)
        if self._use_global_counter:
            self._global_counter += 1
            # Check releases via global counter
            self._check_ghost_exits()
        else:
            # Increment personal counter of the most-imprisoned ghost
            for g in self._ghosts:
                if g.mode == MODE_HOUSE and g.name != "blinky":
                    g.dot_counter += 1
                    break

    def _check_extra_life(self) -> None:
        if not self._extra_life_awarded and self._score >= SCORE_LIFE:
            self._extra_life_awarded = True
            self._lives += 1

    # ── Ghost house exits ─────────────────────────────────────────────────────
    def _check_ghost_exits(self) -> None:
        for g in self._ghosts:
            if g.mode != MODE_HOUSE:
                continue
            if g.name == "blinky":
                # Blinky always starts outside
                continue

            if self._use_global_counter:
                limit = GLOBAL_LIMITS.get(g.name, 999)
                if self._global_counter >= limit:
                    g.release_from_house(self.maze)
                    return   # one at a time
            else:
                if g.dot_counter >= g.dot_limit:
                    g.release_from_house(self.maze)
                    return

    def _force_release(self) -> None:
        for g in self._ghosts:
            if g.mode == MODE_HOUSE:
                g.release_from_house(self.maze)
                return

    # ── Collision ─────────────────────────────────────────────────────────────
    def _check_collisions(self) -> None:
        for g in self._ghosts:
            result = g.check_collision(self._pacman)
            if result == "kill":
                self._state       = "dying"
                self._state_timer = 1.5
                return
            elif result == "eaten":
                pts = SCORE_GHOST[min(self._ghost_combo, 3)]
                self._ghost_combo += 1
                self._score += pts
                g.mode = MODE_EATEN

    # ── Fruit ─────────────────────────────────────────────────────────────────
    def _update_fruit(self, dt: float) -> None:
        if self._fruit_visible:
            self._fruit_timer -= dt
            if self._fruit_timer <= 0:
                self._fruit_visible = False

    # ── Exposed for renderer ──────────────────────────────────────────────────
    @property
    def pacman(self):          return self._pacman
    @property
    def ghosts(self):          return self._ghosts
    @property
    def score(self):           return self._score
    @property
    def lives(self):           return self._lives
    @property
    def level(self):           return self._level
    @property
    def frightened_timer(self): return self._fright_timer
    @property
    def fruit_visible(self):   return self._fruit_visible

    def show_ghost_in_house(self, ghost) -> bool:
        return True   # always draw ghosts in house (they're visible through the door)

    # ── Input ─────────────────────────────────────────────────────────────────
    def handle_input(self, player: int, action: str) -> None:
        if action == "start":
            if self._state == "title":
                self._state = "playing"
            elif self._state == "game_over":
                self._score = 0
                self._lives = 3
                self._level = 1
                self._extra_life_awarded = False
                self._init_level()
                self._state = "playing"
            elif self._state == "playing":
                self._state = "paused"
            elif self._state == "paused":
                self._state = "playing"
            return

        if action == "select":
            if self._state == "playing":
                self._state = "paused"
            elif self._state == "paused":
                self._state = "playing"
            return

        d = _DIR_MAP.get(action)
        if d and self._state == "playing":
            self._pacman.set_direction(d)

    def is_over(self) -> bool:
        return self._state == "game_over"

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings(self) -> list[dict]:
        return []
