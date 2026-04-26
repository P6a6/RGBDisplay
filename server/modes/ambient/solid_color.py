import numpy as np
from base_mode import BaseMode


class SolidColor(BaseMode):
    def __init__(self):
        self._r, self._g, self._b = 255, 0, 0
        self._frame = np.zeros((64, 64, 3), dtype=np.uint8)
        self._dirty = True

    @staticmethod
    def metadata() -> dict:
        return {
            "name": "Solid Color",
            "description": "Fill the display with a single colour",
            "category": "ambient",
        }

    def start(self) -> None:
        self._dirty = True

    def stop(self) -> None:
        pass

    def tick(self, dt: float) -> np.ndarray:
        if self._dirty:
            self._frame[:, :] = (self._r, self._g, self._b)
            self._dirty = False
        return self._frame

    def get_settings(self) -> list[dict]:
        return [
            {
                "key": "color",
                "label": "Color",
                "type": "color",
                "value": "#{:02x}{:02x}{:02x}".format(self._r, self._g, self._b),
            }
        ]

    def apply_setting(self, key: str, value) -> None:
        if key == "color":
            h = str(value).lstrip("#")
            self._r = int(h[0:2], 16)
            self._g = int(h[2:4], 16)
            self._b = int(h[4:6], 16)
            self._dirty = True
