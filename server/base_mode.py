from abc import ABC, abstractmethod
from typing import Any
import numpy as np


class BaseMode(ABC):
    """
    Base class for all display modes.

    Required overrides : metadata(), start(), stop(), tick()
    Optional overrides : handle_input(), get_settings(), apply_setting()
    """

    @staticmethod
    @abstractmethod
    def metadata() -> dict:
        """
        Return a dict describing the mode:
          name        : str   – display name shown in the UI
          description : str   – one-line description
          category    : str   – 'ambient' | 'games'
        """
        ...

    @abstractmethod
    def start(self) -> None:
        """Called once when this mode becomes active."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Called once when this mode is deactivated."""
        ...

    @abstractmethod
    def tick(self, dt: float) -> np.ndarray:
        """
        Called every frame (~30 fps).
        dt  : seconds elapsed since the previous tick.
        Returns a (64, 64, 3) uint8 numpy array, RGB888,
        row-major with visual (0,0) at top-left.
        """
        ...

    def handle_input(self, player: int, action: str) -> None:
        """
        Handle a controller button press.
        player : 0 or 1
        action : 'up' | 'down' | 'left' | 'right' |
                 'a' | 'b' | 'x' | 'y' | 'start' | 'select'
        """
        pass

    def get_settings(self) -> list[dict]:
        """
        Return a list of setting descriptors for the web UI.
        Each dict must have 'key', 'label', 'type', and 'value'.
        Supported types:
          range  – also needs min, max, step
          color  – value is a '#rrggbb' hex string
          select – also needs options list of {value, label} dicts
        Example:
          [{"key": "speed", "label": "Speed", "type": "range",
            "min": 1, "max": 10, "step": 1, "value": 5}]
        """
        return []

    def apply_setting(self, key: str, value: Any) -> None:
        """Apply a setting change sent from the web UI."""
        pass

    def handle_gyro(self, gamma: float, beta: float) -> None:
        """
        Called when the phone's gyroscope sends an update.
        gamma : left/right tilt  (-90 = full left, +90 = full right)
        beta  : front/back tilt  (-90 = face down, +90 = face up)
        Modes that support gyro steering override this.
        """
        pass

    def handle_accel(self, x: float, y: float, z: float) -> None:
        """
        Called when the phone's accelerometer sends an update.
        x, y, z : acceleration in m/s² (gravity removed) in device frame.
        """
        pass

    def is_over(self) -> bool:
        """
        Return True when the mode is sitting on a game-over / end screen
        with nothing for the player to do.  main.py uses this to auto-reset
        the mode to its title screen after 30 s of inactivity.
        Ambient modes leave this as False (never auto-reset).
        """
        return False
