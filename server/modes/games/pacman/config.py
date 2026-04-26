# ── Display ───────────────────────────────────────────────────────────────────
CELL     = 2      # pixels per maze tile
MAZE_W   = 28
MAZE_H   = 31
OX       = 4      # pixel x offset  (64 - 28*2) // 2
OY       = 1      # pixel y offset  (64 - 31*2) // 2

# ── Directions ────────────────────────────────────────────────────────────────
UP    = ( 0, -1)
DOWN  = ( 0,  1)
LEFT  = (-1,  0)
RIGHT = ( 1,  0)
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}
ALL_DIRS = [UP, LEFT, DOWN, RIGHT]   # tie-break order (original arcade)

# ── Colours ───────────────────────────────────────────────────────────────────
C_WALL          = (33,  33, 255)
C_DOT           = (255, 185, 175)
C_PELLET        = (255, 185, 175)
C_DOOR          = (255, 184, 255)
C_PAC           = (255, 255,   0)
C_BLINKY        = (255,   0,   0)
C_PINKY         = (255, 184, 255)
C_INKY          = (  0, 255, 255)
C_CLYDE         = (255, 184,  81)
C_FRIGHT        = (  0, 100, 255)
C_FRIGHT_FLASH  = (255,  50,  50)
C_EYES          = (255, 255, 255)

# ── Speeds  (fraction of base 7.5 tiles/s → tiles per tick at 30fps) ─────────
# Index: 0=pac_normal 1=pac_dot 2=ghost_normal 3=ghost_tunnel
#        4=ghost_fright 5=ghost_eaten
_B = 7.5 / 30   # base tiles per tick (100% speed at 30fps)
SPEEDS = {
    # pac_normal  pac_dot  ghost_normal  ghost_tunnel  ghost_fright  ghost_eaten
    1:  [0.85, 0.75, 0.50, 0.30, 0.30, 1.20],
    2:  [0.90, 0.79, 0.60, 0.35, 0.35, 1.20],
    5:  [1.00, 0.87, 0.75, 0.45, 0.40, 1.20],
    9:  [1.00, 0.87, 0.85, 0.50, 0.00, 1.20],
    21: [0.90, 0.79, 0.90, 0.50, 0.00, 1.20],
}

def get_speeds(level: int) -> list[float]:
    key = 1
    for k in sorted(SPEEDS.keys()):
        if level >= k:
            key = k
    return [v * _B for v in SPEEDS[key]]

# ── Scatter/chase sequence  (mode, seconds) ───────────────────────────────────
INF = float('inf')
SCATTER_CHASE = {
    1: [("scatter",10),("chase",12),("scatter",10),("chase",12),
        ("scatter",8),("chase",15),("scatter",8),("chase",INF)],
    2: [("scatter",8),("chase",15),("scatter",8),("chase",15),
        ("scatter",5),("chase",20),("scatter",5),("chase",INF)],
    5: [("scatter",5),("chase",20),("scatter",5),("chase",20),
        ("scatter",5),("chase",INF)],
}

def get_scatter_chase(level: int) -> list:
    if level <= 1: return SCATTER_CHASE[1]
    if level <= 4: return SCATTER_CHASE[2]
    return SCATTER_CHASE[5]

# ── Frightened duration per level ─────────────────────────────────────────────
FRIGHT_DUR = {1:6,2:5,3:4,4:3,5:2,6:5,7:2,8:2,9:1,10:5,
              11:2,12:1,13:1,14:3,15:1,16:1,17:0,18:1}

def get_fright_dur(level: int) -> float:
    return float(FRIGHT_DUR.get(level, 0))

FRIGHT_FLASH_THRESHOLD = 2.0   # seconds remaining before flash starts

# ── Ghost house dot limits (normal play, per level) ───────────────────────────
# (Pinky always 0, exits immediately)
INKY_LIMIT  = {1: 30, 2: 0}
CLYDE_LIMIT = {1: 60, 2: 50}

def get_dot_limit(name: str, level: int) -> int:
    if name in ("blinky", "pinky"):
        return 0
    if name == "inky":
        return INKY_LIMIT.get(level, 0)
    if name == "clyde":
        return CLYDE_LIMIT.get(level, 0)
    return 0

# After losing a life, global dot counter limits:
GLOBAL_LIMITS = {"pinky": 7, "inky": 17, "clyde": 32}

# Force-release timeout (seconds without a dot eaten)
FORCE_RELEASE_TIMEOUT = 4.0

# ── Scores ────────────────────────────────────────────────────────────────────
SCORE_DOT    = 10
SCORE_PELLET = 50
SCORE_GHOST  = [200, 400, 800, 1600]
SCORE_LIFE   = 10000   # extra life threshold

# Scatter target corners (off-maze tiles)
SCATTER_TARGETS = {
    "blinky": (25, -3),
    "pinky":  ( 2, -3),
    "inky":   (27,  31),
    "clyde":  ( 0,  31),
}

# Intersections where ghosts cannot choose UP (original arcade restriction)
NO_UP_TILES = {(12, 14), (15, 14), (12, 26), (15, 26)}

# Ghost house: re-entry target, home bounce range
HOUSE_ENTRY   = (13, 14)
HOUSE_Y_MIN   = 13.5
HOUSE_Y_MAX   = 15.0

# Pac-Man start — bottom-centre corridor (row 26, cols 13-14 opened in maze)
PAC_START = (13, 26)
PAC_START_DIR = LEFT

# Ghost starts
GHOST_STARTS = {
    "blinky": {"tile": (13, 11), "outside": True},
    "pinky":  {"tile": (13, 14), "outside": False},
    "inky":   {"tile": (11, 14), "outside": False},
    "clyde":  {"tile": (15, 14), "outside": False},
}

# Fruit tile and eat durations
FRUIT_TILE    = (13, 20)
FRUIT_DOTS    = [70, 170]
FRUIT_VISIBLE = 9.5   # seconds
FRUIT_SCORES  = {1:100,2:300,3:500,4:500,5:700,6:700,
                 7:1000,8:1000,9:2000,10:2000,11:3000,12:3000}

# 3×5 font for score overlay
FONT: dict[str, list[int]] = {
    ' ': [0,0,0],
    'A': [15,20,15],'B': [31,21,10],'C': [14,17,17],'D': [31,17,14],
    'E': [31,21,17],'F': [31,20,16],'G': [14,21,23],'H': [31,4,31],
    'I': [17,31,17],'J': [2,17,30], 'K': [31,4,27], 'L': [31,1,1],
    'M': [31,24,4,24,31],'N': [31,8,4,31],
    'O': [14,17,14],'P': [31,20,24],'Q': [14,17,15],'R': [31,20,11],
    'S': [9,21,18], 'T': [16,31,16],'U': [30,1,30], 'V': [28,3,28],
    'W': [31,2,4,2,31],'X': [27,4,27],'Y': [24,7,24],'Z': [19,21,9],
    '0': [14,17,14],'1': [9,31,1],  '2': [23,21,29],'3': [21,21,31],
    '4': [28,4,31], '5': [29,21,23],'6': [31,21,7], '7': [16,19,28],
    '8': [10,21,10],'9': [12,21,14],'-': [4,4,4],
}
