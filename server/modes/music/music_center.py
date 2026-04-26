import numpy as np
import main as _server
from base_mode import BaseMode
from modes.music._shared import HEIGHT, N_BARS, FRAC_LUT, FREQ_TILT, process_bands

WIDTH = 64
# 32 bands mapped symmetrically: band 0 (bass) → columns 31+32 (centre)
#                                  band 31 (treble) → columns 0+63 (edges)
N_HALF = 32


class MusicCenter(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Music Center",
            "description": "Symmetric EQ — bass pumps in the centre, treble on the edges",
            "category": "music",
        }

    def __init__(self):
        self._sensitivity = 10
        self._decay_speed = 5
        # Work with 32 bands (merge pairs from the 64-band input)
        self._bars  = np.zeros(N_HALF, dtype=np.float32)
        self._peaks = np.zeros(N_HALF, dtype=np.float32)
        self._hold  = np.zeros(N_HALF, dtype=np.int32)

    def start(self) -> None:
        self._bars[:]  = 0.0
        self._peaks[:] = 0.0
        self._hold[:]  = 0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        gain  = self._sensitivity / 10.0
        decay = (0.015 + self._decay_speed * 0.025) * dt * 60

        # Merge 64 client bands → 32 display bands (average adjacent pairs)
        raw64 = _server._audio_bands
        raw32 = (raw64[0::2] + raw64[1::2]) * 0.5

        # Tilt: use every-other entry of FREQ_TILT
        tilt32 = FREQ_TILT[0::2]
        tilted = raw32 * tilt32 * gain
        compressed = np.tanh(tilted * 1.8) * 0.92

        rising       = compressed > self._bars
        self._bars   = np.where(rising,
                                self._bars + (compressed - self._bars) * 0.88,
                                np.maximum(compressed, self._bars - decay))
        np.clip(self._bars, 0.0, 1.0, out=self._bars)

        # Peak hold
        risen        = self._bars > self._peaks
        self._peaks  = np.where(risen, self._bars, self._peaks)
        self._hold   = np.where(risen, 35, self._hold)
        holding      = self._hold > 0
        self._hold   = np.where(holding, self._hold - 1, 0)
        self._peaks  = np.where(~holding, self._peaks * 0.94, self._peaks)
        np.clip(self._peaks, 0.0, 1.0, out=self._peaks)

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        for i in range(N_HALF):
            # Band 0 = bass → centre columns (31, 32)
            # Band 31 = treble → edge columns (0, 63)
            left_col  = 31 - i   # 31 (bass/centre) → 0 (treble/edge)
            right_col = 32 + i   # 32 (bass/centre) → 63 (treble/edge)

            h = int(self._bars[i] * HEIGHT)
            if h > 0:
                y_top = HEIGHT - h
                for row in range(y_top, HEIGHT):
                    frac_idx = int((HEIGHT - 1 - row) / h * 100)
                    c = FRAC_LUT[min(frac_idx, 100)]
                    frame[row, left_col]  = c
                    frame[row, right_col] = c

            # Peak dot
            p = self._peaks[i]
            if p > 0.01:
                py = max(0, min(HEIGHT - 1, int((1.0 - p) * HEIGHT)))
                frame[py, left_col]  = (255, 255, 255)
                frame[py, right_col] = (255, 255, 255)

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
