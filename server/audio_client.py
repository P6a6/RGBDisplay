"""
audio_client.py — RGB Display music visualizer audio capture client.

Run this on the PC that is playing music (NOT on the home server).
Captures system audio via PulseAudio/PipeWire monitor source, computes
40 mel-scale frequency bands, and streams them to the display server via UDP.

Linux:   uses pacat (PulseAudio/PipeWire) — always works
Windows: uses sounddevice WASAPI loopback (pip install sounddevice)

Usage:
    python audio_client.py --server 192.168.0.41
    python audio_client.py --server 192.168.0.41 --device "alsa_output...monitor"
    python audio_client.py --list-devices
    python audio_client.py --server 192.168.0.41 --sensitivity 1.5
"""

import argparse
import socket
import struct
import subprocess
import sys
import time

import numpy as np

# ── Constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE  = 48000
CHANNELS     = 2
BYTES_EACH   = 2           # s16le
FRAME_BYTES  = CHANNELS * BYTES_EACH

FFT_SIZE     = 4096
HOP_SIZE     = 512
N_BANDS      = 32
N_SEND       = 64          # UDP payload always 64 floats
MIN_FREQ     = 60.0
MAX_FREQ     = 16000.0
MAGIC        = b'MUSC'

_freq_edges = np.logspace(np.log10(MIN_FREQ), np.log10(MAX_FREQ), N_BANDS + 1)
_bin_edges  = np.clip((_freq_edges / SAMPLE_RATE * FFT_SIZE).astype(int),
                      1, FFT_SIZE // 2)
_hann       = np.hanning(FFT_SIZE).astype(np.float32)


# ── Band computer ─────────────────────────────────────────────────────────────
class BandComputer:
    """
    Per-band independent normalization.

    Each frequency band tracks its own recent peak level and normalises
    against a dynamic window 45 dB below that peak. This means:
    - Bass bands calibrate to bass content independently from treble
    - All active bands show dynamics — quiet treble moves just as much as loud bass
    - True silence (below -65 dBFS absolute floor) shows as zero

    Asymmetric IIR: fast attack so onsets are immediate, moderate decay
    so bars return to baseline between beats. Server controls hang time.
    """
    RANGE_DB    = 45.0   # dB of dynamic range shown per band
    ABS_FLOOR   = -65.0  # absolute dBFS floor — below this is silence/noise
    PEAK_DECAY  = 0.9997 # per-band peak drops ~0.5 dB/s — very slow, ~30s calibration
    ATTACK      = 0.75
    DECAY       = 0.40

    def __init__(self):
        self._buf     = np.zeros(FFT_SIZE, dtype=np.float32)
        self._peak_db = np.full(N_BANDS, self.ABS_FLOOR, dtype=np.float32)
        self._smooth  = np.zeros(N_BANDS, dtype=np.float32)

    def push(self, mono_chunk: np.ndarray, sensitivity: float) -> np.ndarray:
        n = len(mono_chunk)
        self._buf = np.roll(self._buf, -n)
        self._buf[-n:] = mono_chunk

        mag = np.abs(np.fft.rfft(self._buf * _hann))

        # Per-band mean magnitude → dB
        bands_db = np.zeros(N_BANDS, dtype=np.float32)
        for i in range(N_BANDS):
            lo = _bin_edges[i]
            hi = max(_bin_edges[i] + 1, _bin_edges[i + 1])
            m  = float(np.mean(mag[lo:hi]))
            bands_db[i] = 20.0 * np.log10(max(m, 1e-9))

        # Per-band peak tracking — slow decay so calibration is stable
        self._peak_db = np.maximum(self._peak_db * self.PEAK_DECAY +
                                   (1 - self.PEAK_DECAY) * bands_db,
                                   bands_db)

        # Dynamic floor = peak minus RANGE_DB, but never below ABS_FLOOR
        floor_db = np.maximum(self._peak_db - self.RANGE_DB, self.ABS_FLOOR)

        # Normalise: 0 = at floor, 1 = at peak
        norm = np.clip((bands_db - floor_db) / self.RANGE_DB, 0.0, 1.0)
        norm = norm * sensitivity

        # Fast-attack IIR to smooth FFT noise without hiding transients
        rising       = norm > self._smooth
        self._smooth = np.where(
            rising,
            self._smooth + (norm - self._smooth) * self.ATTACK,
            self._smooth + (norm - self._smooth) * self.DECAY,
        )
        np.clip(self._smooth, 0.0, 1.0, out=self._smooth)
        return self._smooth.astype(np.float32)


# ── Device helpers ────────────────────────────────────────────────────────────
def _list_pulse_sources() -> list[str]:
    try:
        out = subprocess.check_output(['pactl', 'list', 'short', 'sources'],
                                      text=True, stderr=subprocess.DEVNULL)
        return [line.split('\t')[1] for line in out.splitlines() if '\t' in line]
    except Exception:
        return []

def _best_monitor(sources: list[str]) -> str | None:
    running = [s for s in sources if 'monitor' in s]
    for s in running:
        if 'analog-stereo.monitor' in s:
            return s
    return running[0] if running else None

def list_devices():
    sources = _list_pulse_sources()
    print("PulseAudio/PipeWire sources (use --device to pick one):")
    for s in sources:
        print(f"  {s}")
    sys.exit(0)


# ── Linux capture via pacat ───────────────────────────────────────────────────
def run_linux(server: str, port: int, device: str | None, sensitivity: float):
    sources = _list_pulse_sources()
    if not sources:
        print("ERROR: pactl not found or no PulseAudio/PipeWire sources.")
        sys.exit(1)

    source = device or _best_monitor(sources)
    if source is None:
        print("ERROR: no monitor source found. Run --list-devices.")
        sys.exit(1)

    print(f"Capturing from: {source}")
    print(f"Streaming to:   {server}:{port}   sensitivity: {sensitivity:.1f}×")
    print(f"Mel bands: {N_BANDS}   FFT size: {FFT_SIZE}   hop: {HOP_SIZE}")

    cmd = [
        'pacat', '--record',
        f'--device={source}',
        '--format=s16le',
        f'--rate={SAMPLE_RATE}',
        f'--channels={CHANNELS}',
        '--latency-msec=20',
    ]

    sock      = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    computer  = BandComputer()
    hop_bytes = HOP_SIZE * FRAME_BYTES
    send_interval = 1.0 / 60
    last_send     = 0.0

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    print("Streaming... Press Ctrl+C to stop.\n")
    try:
        raw_buf = b''
        while True:
            chunk = proc.stdout.read(hop_bytes - len(raw_buf))
            if not chunk:
                break
            raw_buf += chunk
            if len(raw_buf) < hop_bytes:
                continue

            pcm     = np.frombuffer(raw_buf[:hop_bytes], dtype='<i2').astype(np.float32)
            raw_buf = raw_buf[hop_bytes:]
            mono    = (pcm[0::2] + pcm[1::2]) * 0.5 / 32768.0

            bands = computer.push(mono, sensitivity)

            # Zero-pad to N_SEND floats so server protocol stays the same
            payload = np.zeros(N_SEND, dtype=np.float32)
            payload[:N_BANDS] = bands

            now = time.monotonic()
            if now - last_send >= send_interval:
                sock.sendto(MAGIC + struct.pack('64f', *payload), (server, port))
                last_send = now

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        proc.terminate()


# ── Windows capture via sounddevice WASAPI loopback ──────────────────────────
def run_windows(server: str, port: int, device: str | None, sensitivity: float):
    try:
        import sounddevice as sd
    except ImportError:
        print("ERROR: install sounddevice:  pip install sounddevice")
        sys.exit(1)

    dev_idx = None
    if device:
        for i, d in enumerate(sd.query_devices()):
            if device.lower() in d['name'].lower() and d['max_input_channels'] > 0:
                dev_idx = i
                break
    else:
        for i, d in enumerate(sd.query_devices()):
            name = d['name'].lower()
            if d['max_input_channels'] > 0 and any(k in name for k in
                    ('stereo mix', 'loopback', 'what u hear', 'wave out')):
                dev_idx = i
                break

    if dev_idx is None:
        print("ERROR: no loopback device found. Run --list-devices.")
        sys.exit(1)

    print(f"Capturing from device index {dev_idx}: {sd.query_devices(dev_idx)['name']}")
    print(f"Streaming to: {server}:{port}   sensitivity: {sensitivity:.1f}×")

    sock      = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    computer  = BandComputer()
    send_int  = 1.0 / 60
    last_send = 0.0
    buf       = []

    def cb(indata, frames, t, status):
        mono = (indata[:, 0] + indata[:, 1]) * 0.5 if indata.shape[1] > 1 else indata[:, 0]
        buf.extend(mono.tolist())

    with sd.InputStream(device=dev_idx, channels=2, samplerate=SAMPLE_RATE,
                        blocksize=HOP_SIZE, dtype='float32', callback=cb):
        print("Streaming... Press Ctrl+C to stop.")
        try:
            while True:
                if len(buf) >= HOP_SIZE:
                    chunk = np.array(buf[:HOP_SIZE], dtype=np.float32)
                    del buf[:HOP_SIZE]
                    bands = computer.push(chunk, sensitivity)
                    payload = np.zeros(N_SEND, dtype=np.float32)
                    payload[:N_BANDS] = bands
                    now = time.monotonic()
                    if now - last_send >= send_int:
                        sock.sendto(MAGIC + struct.pack('64f', *payload), (server, port))
                        last_send = now
                else:
                    time.sleep(0.002)
        except KeyboardInterrupt:
            print("\nStopped.")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="RGB Display audio visualizer client")
    ap.add_argument('--server',       default='192.168.0.41')
    ap.add_argument('--port',   type=int, default=5008)
    ap.add_argument('--device',       default=None)
    ap.add_argument('--sensitivity', type=float, default=1.0,
                    help='Gain multiplier (default 1.0)')
    ap.add_argument('--list-devices', action='store_true')
    args = ap.parse_args()

    if args.list_devices:
        list_devices()

    if sys.platform == 'win32':
        run_windows(args.server, args.port, args.device, args.sensitivity)
    else:
        run_linux(args.server, args.port, args.device, args.sensitivity)


if __name__ == '__main__':
    main()
