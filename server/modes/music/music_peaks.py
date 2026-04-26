import numpy as np
import main as _server
from base_mode import BaseMode
from modes.music._shared import HEIGHT, N_BANDS, FRAC_LUT, process_bands



WIDTH        = 64
HOLD_FRAMES  = 30
PEAK_GRAVITY = 0.92

_BAR_STARTS = (np.arange(N_BANDS) * 2).astype(int)


class MusicPeaks(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Music Peaks",
            "description": "Mel-scale bars with white peak-hold dot — rises instantly, holds, then falls",
            "category": "music",
        }

    def __init__(self):
        self._sensitivity = 10
        self._decay_speed = 5
        self._bars  = np.zeros(N_BANDS, dtype=np.float32)
        self._peaks = np.zeros(N_BANDS, dtype=np.float32)
        self._hold  = np.zeros(N_BANDS, dtype=np.int32)

    def start(self) -> None:
        self._bars[:]  = 0.0
        self._peaks[:] = 0.0
        self._hold[:]  = 0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        decay = (0.03 + self._decay_speed * 0.05) * dt * 60
        gain  = self._sensitivity / 10.0
        process_bands(_server._audio_bands, self._bars, decay, gain)

        # Peak hold + gravity
        risen        = self._bars > self._peaks
        self._peaks  = np.where(risen, self._bars, self._peaks)
        self._hold   = np.where(risen, HOLD_FRAMES, self._hold)
        holding      = self._hold > 0
        self._hold   = np.where(holding, self._hold - 1, 0)
        self._peaks  = np.where(~holding, self._peaks * PEAK_GRAVITY, self._peaks)
        np.clip(self._peaks, 0.0, 1.0, out=self._peaks)

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        for i, x in enumerate(_BAR_STARTS):
            h = int(self._bars[i] * HEIGHT)
            if h > 0:
                y_top = HEIGHT - h
                for row in range(y_top, HEIGHT):
                    frac_idx = int((HEIGHT - 1 - row) / h * 100)
                    c = FRAC_LUT[min(frac_idx, 100)]
                    frame[row, x]     = c
                    frame[row, x + 1] = c

            p = self._peaks[i]
            if p > 0.01:
                py = max(0, min(HEIGHT - 1, int((1.0 - p) * HEIGHT)))
                frame[py, x]     = (255, 255, 255)
                frame[py, x + 1] = (255, 255, 255)

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
