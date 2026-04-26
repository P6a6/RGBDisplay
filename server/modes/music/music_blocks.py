import numpy as np
import main as _server
from base_mode import BaseMode
from modes.music._shared import HEIGHT, N_BANDS, FRAC_LUT

WIDTH     = 64
N_BLOCKS  = 16     # 16 chunky bars
# Each block: 3px bar + 1px gap = 4px × 16 = 64px exactly
BLOCK_W   = 3
GAP_W     = 1
HOLD_FRAMES  = 28
PEAK_GRAVITY = 0.91

# Map 40 mel bands → 16 blocks (average adjacent mel bands)
_BANDS_PER_BLOCK = N_BANDS / N_BLOCKS   # 2 bands per block (32/16)


def _mel_to_blocks(mel: np.ndarray) -> np.ndarray:
    """Average mel bands into N_BLOCKS display blocks."""
    out = np.zeros(N_BLOCKS, dtype=np.float32)
    for b in range(N_BLOCKS):
        lo = int(round(b * _BANDS_PER_BLOCK))
        hi = int(round((b + 1) * _BANDS_PER_BLOCK))
        hi = max(hi, lo + 1)
        out[b] = np.max(mel[lo:min(hi, N_BANDS)])   # max preserves transients
    return out


class MusicBlocks(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Music Blocks",
            "description": "16 wide chunky bars with peak-hold dots — retro arcade look",
            "category": "music",
        }

    def __init__(self):
        self._sensitivity = 10
        self._decay_speed = 5
        self._bars  = np.zeros(N_BLOCKS, dtype=np.float32)
        self._peaks = np.zeros(N_BLOCKS, dtype=np.float32)
        self._hold  = np.zeros(N_BLOCKS, dtype=np.int32)

    def start(self) -> None:
        self._bars[:]  = 0.0
        self._peaks[:] = 0.0
        self._hold[:]  = 0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        decay  = (0.03 + self._decay_speed * 0.05) * dt * 60
        gain   = self._sensitivity / 10.0
        raw    = np.clip(_server._audio_bands[:N_BANDS] * gain, 0.0, 1.0)
        blocks = _mel_to_blocks(raw)

        rising      = blocks > self._bars
        self._bars  = np.where(
            rising,
            self._bars + (blocks - self._bars) * 0.80,
            np.maximum(0.0, self._bars - decay),
        )
        np.clip(self._bars, 0.0, 1.0, out=self._bars)

        # Peak hold + gravity
        risen        = self._bars > self._peaks
        self._peaks  = np.where(risen, self._bars, self._peaks)
        self._hold   = np.where(risen, HOLD_FRAMES, self._hold)
        holding      = self._hold > 0
        self._hold   = np.where(holding, self._hold - 1, 0)
        self._peaks  = np.where(~holding, self._peaks * PEAK_GRAVITY, self._peaks)
        np.clip(self._peaks, 0.0, 1.0, out=self._peaks)

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        for b in range(N_BLOCKS):
            x = b * (BLOCK_W + GAP_W)
            h = int(self._bars[b] * HEIGHT)

            if h > 0:
                y_top = HEIGHT - h
                for row in range(y_top, HEIGHT):
                    frac_idx = int((HEIGHT - 1 - row) / h * 100)
                    c = FRAC_LUT[min(frac_idx, 100)]
                    frame[row, x:x + BLOCK_W] = c

            # Peak dot: white 3-pixel stripe
            p = self._peaks[b]
            if p > 0.01:
                py = max(0, min(HEIGHT - 1, int((1.0 - p) * HEIGHT)))
                frame[py, x:x + BLOCK_W] = (255, 255, 255)

        return frame

    def get_settings(self) -> list[dict]:
        return [
            {"key": "sensitivity", "label": "Sensitivity", "type": "range",
             "min": 1, "max": 20, "step": 1, "value": self._sensitivity},
            {"key": "decay", "label": "Bar Decay", "type": "range",
             "min": 1, "max": 10, "step": 1, "value": self._decay_speed},
        ]

    def apply_setting(self, key: str, value) -> None:
        if key == "sensitivity":
            self._sensitivity = max(1, min(20, int(value)))
        elif key == "decay":
            self._decay_speed = max(1, min(10, int(value)))
