import socket


class StateSender:
    """Sends a 1-byte display on/off state to the ESP32 (port 5007).
    0 = display off, 1 = display on."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, on: bool) -> None:
        try:
            self._sock.sendto(bytes([1 if on else 0]), (self.host, self.port))
        except OSError:
            pass
