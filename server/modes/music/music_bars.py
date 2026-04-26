import numpy as np
import main as _server
from base_mode import BaseMode
from modes.music._shared import HEIGHT, N_BANDS, FRAC_LUT, process_bands

WIDTH = 64
# 32 bars × 2px each = 64px — fills the display exactly with no gaps
_BAR_STARTS = (np.arange(N_BANDS) * 2).astype(int)


class MusicBars(BaseMode):

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Music Bars",
            "description": "40 mel-scale bars across the display — blue→red gradient per bar",
            "category": "music",
        }

    def __init__(self):
        self._sensitivity = 10
        self._decay_speed = 5
        self._bars = np.zeros(N_BANDS, dtype=np.float32)

    def start(self) -> None:
        self._bars[:] = 0.0

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        decay = (0.03 + self._decay_speed * 0.05) * dt * 60
        gain  = self._sensitivity / 10.0
        process_bands(_server._audio_bands, self._bars, decay, gain)

        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        for i, x in enumerate(_BAR_STARTS):
            h = int(self._bars[i] * HEIGHT)
            if h <= 0:
                continue
            y_top = HEIGHT - h
            for row in range(y_top, HEIGHT):
                frac_idx = int((HEIGHT - 1 - row) / h * 100)
                c = FRAC_LUT[min(frac_idx, 100)]
                frame[row, x]     = c
                frame[row, x + 1] = c

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
