import socket


class BrightnessSender:
    """
    Sends a single brightness byte (0–255) via UDP to the ESP32
    on port 5006.  The ESP32 calls dma->setBrightness8() immediately.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, brightness: int) -> None:
        value = max(0, min(255, int(brightness)))
        try:
            self._sock.sendto(bytes([value]), (self.host, self.port))
        except OSError:
            pass
