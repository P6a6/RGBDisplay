import socket
import struct
import numpy as np

WIDTH = 64
HEIGHT = 64
FRAME_BYTES = WIDTH * HEIGHT * 3  # 12 288

# Payload per chunk — keep well below WiFi MTU (1472 bytes) to leave room
# for the 4-byte header.  12288 / 1396 = 9 chunks (the last one is smaller).
CHUNK_PAYLOAD = 1396
HEADER_SIZE   = 4   # frame_id(2) + chunk_index(1) + total_chunks(1)

_total_chunks = -(-FRAME_BYTES // CHUNK_PAYLOAD)   # ceil division → 9


class FrameSender:
    """
    Sends a 64×64 RGB888 frame as MTU-safe UDP chunks.

    Each chunk has a 4-byte header:
        [frame_id: uint16 LE] [chunk_index: uint8] [total_chunks: uint8]

    The ESP32 uses the header to detect frame boundaries and discard
    out-of-order or stale chunks, preventing buffer-sync corruption.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host       = host
        self.port       = port
        self._sock      = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._frame_id  = 0   # wraps at 65535

    def send(self, frame: np.ndarray) -> None:
        """Send a (64, 64, 3) uint8 frame as MTU-safe, header-tagged chunks."""
        data = frame.astype(np.uint8, copy=False).tobytes()
        fid  = self._frame_id
        try:
            for idx in range(_total_chunks):
                start   = idx * CHUNK_PAYLOAD
                payload = data[start:start + CHUNK_PAYLOAD]
                header  = struct.pack('<HBB', fid, idx, _total_chunks)
                self._sock.sendto(header + payload, (self.host, self.port))
        except OSError:
            pass
        self._frame_id = (self._frame_id + 1) & 0xFFFF

    def close(self) -> None:
        self._sock.close()
