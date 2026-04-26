"""Shared helpers for music visualizer modes."""
import numpy as np

HEIGHT  = 64
N_BANDS = 32

# ── Per-fraction colour lookup (101 steps, 0=bar bottom, 100=bar top) ─────────
# Color is by position WITHIN the bar so even short bars show the full gradient.
def _make_frac_lut():
    lut = np.zeros((101, 3), dtype=np.uint8)
    for i in range(101):
        f = i / 100.0
        if f < 0.25:
            t = f / 0.25
            lut[i] = (0, int(20 + 80*t), int(160 + 95*t))    # deep blue → blue
        elif f < 0.50:
            t = (f - 0.25) / 0.25
            lut[i] = (0, int(100 + 155*t), int(255 - 255*t))  # blue → cyan → green
        elif f < 0.72:
            t = (f - 0.50) / 0.22
            lut[i] = (int(200*t), 255, 0)                      # green → yellow
        elif f < 0.88:
            t = (f - 0.72) / 0.16
            lut[i] = (int(200 + 55*t), int(255 - 200*t), 0)   # yellow → orange
        else:
            t = (f - 0.88) / 0.12
            lut[i] = (255, int(55 - 55*t), 0)                  # orange → red
    return lut

FRAC_LUT = _make_frac_lut()

def process_bands(raw: np.ndarray, bars: np.ndarray,
                  decay_per_frame: float, gain: float = 1.0) -> np.ndarray:
    target  = np.clip(raw[:N_BANDS] * gain, 0.0, 1.0)
    rising  = target > bars
    bars[:] = np.where(
        rising,
        bars + (target - bars) * 0.80,
        np.maximum(0.0, bars - decay_per_frame),
    )
    return bars


def draw_bar(frame: np.ndarray, col: int, h: int):
    """Draw a single-pixel-wide bar of height h in column col using FRAC_LUT."""
    if h <= 0:
        return
    y_top = HEIGHT - h
    for row in range(y_top, HEIGHT):
        frac_idx = int((HEIGHT - 1 - row) / h * 100)
        frame[row, col] = FRAC_LUT[min(frac_idx, 100)]


def draw_block_bar(frame: np.ndarray, x_start: int, width: int, h: int):
    """Draw a multi-pixel-wide bar starting at x_start with given pixel width."""
    if h <= 0:
        return
    y_top = HEIGHT - h
    for row in range(y_top, HEIGHT):
        frac_idx = int((HEIGHT - 1 - row) / h * 100)
        c = FRAC_LUT[min(frac_idx, 100)]
        frame[row, x_start:x_start + width] = c
