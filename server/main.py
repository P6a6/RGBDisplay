"""
RGB Display Server — FastAPI entry point.

Lifecycle:
  startup  → discover plugins, send default brightness, start game loop
  running  → tick active mode at ~30 fps, send frames + WS broadcasts
  shutdown → cancel tasks, close sockets, call mode.stop()
"""

import asyncio
import json
import socket
import struct
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brightness_sender import BrightnessSender
from frame_sender import FrameSender
from plugin_manager import PluginManager
from state_sender import StateSender
from websocket_manager import WebSocketManager

# ── Config ────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent
with open(_ROOT / "config.yaml") as _f:
    _cfg = yaml.safe_load(_f)

_ESP_IP = _cfg["esp32"]["ip"]
_FRAME_PORT = _cfg["esp32"]["frame_port"]
_BRIGHTNESS_PORT = _cfg["esp32"]["brightness_port"]
_STATE_PORT: int = _cfg["esp32"].get("state_port", 5007)
_FPS: int = _cfg["display"]["fps"]
_DEFAULT_BRIGHTNESS: int = _cfg["display"]["default_brightness"]

# ── Subsystems ────────────────────────────────────────────────────────────────
plugins = PluginManager(_ROOT / "modes")
frame_sender = FrameSender(_ESP_IP, _FRAME_PORT)
brightness_sender = BrightnessSender(_ESP_IP, _BRIGHTNESS_PORT)
state_sender = StateSender(_ESP_IP, _STATE_PORT)
ws_manager = WebSocketManager()

_current_mode_id: str | None = None
_current_mode = None
_current_brightness: int = _DEFAULT_BRIGHTNESS
_display_on: bool = True

_BLANK = np.zeros((64, 64, 3), dtype=np.uint8)

_GAME_OVER_TIMEOUT = 30.0   # seconds on game-over screen before auto-reset to title
_game_over_timer: float = 0.0   # accumulates while mode.is_over() is True
_last_input_time: float = 0.0   # monotonic, updated on every player input

# ── Audio bands (shared with music modes) ─────────────────────────────────────
# Shape (64,), float32, range 0–1. Updated by UDP listener on port 5008.
# Music modes import this module and read _audio_bands directly.
_audio_bands: np.ndarray = np.zeros(64, dtype=np.float32)
_audio_last_rx: float    = 0.0   # monotonic time of last valid packet
_AUDIO_PORT = 5008
_AUDIO_MAGIC = b'MUSC'

# ── Persistent settings store ─────────────────────────────────────────────────
_SETTINGS_FILE = _ROOT / "settings_store.json"

def _load_settings_store() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text())
    except Exception:
        return {}

def _save_settings_store(store: dict) -> None:
    try:
        _SETTINGS_FILE.write_text(json.dumps(store, indent=2))
    except Exception as e:
        print(f"[settings] save error: {e}")

_settings_store: dict = _load_settings_store()


# ── Mode helpers ──────────────────────────────────────────────────────────────
def _activate_mode(mode_id: str) -> bool:
    global _current_mode_id, _current_mode
    if mode_id not in plugins.modes:
        print(f"[main] mode activation FAILED — unknown id: {mode_id!r}")
        return False
    print(f"[main] activating mode: {mode_id!r}")
    if _current_mode is not None:
        try:
            _current_mode.stop()
        except Exception as exc:
            print(f"[main] mode.stop() error: {exc}")
    _current_mode = plugins.modes[mode_id]()
    _current_mode_id = mode_id
    try:
        _current_mode.start()
    except Exception as exc:
        print(f"[main] mode.start() error: {exc}")
    # Restore saved settings for this mode
    for k, v in _settings_store.get(mode_id, {}).items():
        try:
            _current_mode.apply_setting(k, v)
        except Exception as exc:
            print(f"[settings] restore {mode_id} {k}={v!r} failed: {exc}")
    print(f"[main] mode active: {mode_id!r}")
    return True


def _persist_setting(mode_id: str, key: str, value: Any) -> None:
    if mode_id not in _settings_store:
        _settings_store[mode_id] = {}
    _settings_store[mode_id][key] = value
    _save_settings_store(_settings_store)


def _mode_list() -> list[dict]:
    result = []
    for mid, cls in plugins.modes.items():
        meta = dict(cls.metadata())
        meta["id"] = mid
        meta["active"] = mid == _current_mode_id
        result.append(meta)
    return result


# ── Game loop ─────────────────────────────────────────────────────────────────
async def _game_loop() -> None:
    global _display_on, _game_over_timer
    interval = 1.0 / _FPS
    loop = asyncio.get_event_loop()
    last = loop.time()
    frames_sent = 0
    last_report = loop.time()
    print(f"[loop] game loop started — target {_FPS} fps, sending to {_ESP_IP}:{_FRAME_PORT}")
    while True:
        now = loop.time()
        dt = now - last
        last = now
        if _display_on and _current_mode is not None:
            try:
                # Auto-reset game-over screen after 30 s of no input
                if _current_mode.is_over():
                    _game_over_timer += dt
                    if _game_over_timer >= _GAME_OVER_TIMEOUT:
                        _game_over_timer = 0.0
                        _current_mode.start()
                else:
                    _game_over_timer = 0.0

                frame = _current_mode.tick(dt)
                frame_sender.send(frame)
                frames_sent += 1
            except Exception as exc:
                print(f"[loop] tick error: {exc}")
                frame_sender.send(_BLANK)
        if _display_on and now - last_report >= 5.0:
            print(f"[loop] {frames_sent} frames sent in last 5s  (mode={_current_mode_id!r}  target={_ESP_IP}:{_FRAME_PORT})")
            frames_sent = 0
            last_report = now
        if not _display_on:
            last_report = loop.time()
            frames_sent = 0
        elapsed = loop.time() - now
        await asyncio.sleep(max(0.0, interval - elapsed))


# ── Audio UDP listener ────────────────────────────────────────────────────────
class _AudioProtocol(asyncio.DatagramProtocol):
    def datagram_received(self, data: bytes, addr):
        global _audio_bands, _audio_last_rx
        if len(data) == 260 and data[:4] == _AUDIO_MAGIC:
            _audio_bands = np.frombuffer(data[4:], dtype='<f4').copy()
            _audio_last_rx = time.monotonic()

async def _audio_decay_loop():
    """When no audio packets arrive, smoothly decay bands to zero."""
    while True:
        await asyncio.sleep(0.1)
        if time.monotonic() - _audio_last_rx > 2.0:
            global _audio_bands
            _audio_bands = (_audio_bands * 0.85).astype(np.float32)

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    plugins.discover()
    brightness_sender.send(_current_brightness)
    state_sender.send(True)
    loop_task  = asyncio.create_task(_game_loop())
    decay_task = asyncio.create_task(_audio_decay_loop())
    # Start audio UDP listener
    loop = asyncio.get_event_loop()
    try:
        audio_transport, _ = await loop.create_datagram_endpoint(
            _AudioProtocol, local_addr=('0.0.0.0', _AUDIO_PORT))
        print(f"[audio] UDP listener on port {_AUDIO_PORT} OK")
    except Exception as e:
        audio_transport = None
        print(f"[audio] UDP listener FAILED: {e}")
    yield
    loop_task.cancel(); decay_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    try:
        await decay_task
    except asyncio.CancelledError:
        pass
    if audio_transport:
        audio_transport.close()
    frame_sender.close()
    if _current_mode is not None:
        try:
            _current_mode.stop()
        except Exception:
            pass


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="RGB Display", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=_ROOT / "static"), name="static")


# ── HTTP API ──────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse(_ROOT / "static" / "index.html")


@app.get("/cert")
async def download_cert():
    """Download the self-signed cert so you can install it on iOS."""
    cert = _ROOT / "cert.pem"
    if not cert.exists():
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("No cert.pem found on server.", status_code=404)
    return FileResponse(cert, media_type="application/x-pem-file",
                        filename="rgbdisplay.pem")


@app.get("/api/modes")
async def list_modes():
    return _mode_list()


@app.get("/api/state")
async def get_state():
    return {"mode_id": _current_mode_id, "brightness": _current_brightness, "display_on": _display_on}


@app.get("/api/settings")
async def get_settings():
    if _current_mode is None:
        return []
    return _current_mode.get_settings()


class ModeRequest(BaseModel):
    mode_id: str


@app.post("/api/mode")
async def activate_mode(req: ModeRequest):
    ok = _activate_mode(req.mode_id)
    if not ok:
        return {"error": "Mode not found"}
    await ws_manager.broadcast({"type": "mode_changed", "mode_id": _current_mode_id})
    return {"ok": True, "mode_id": _current_mode_id}


class BrightnessRequest(BaseModel):
    value: int


@app.post("/api/brightness")
async def set_brightness(req: BrightnessRequest):
    global _current_brightness
    _current_brightness = max(0, min(255, req.value))
    brightness_sender.send(_current_brightness)
    await ws_manager.broadcast({"type": "brightness", "value": _current_brightness})
    return {"ok": True, "brightness": _current_brightness}


class SettingRequest(BaseModel):
    key: str
    value: Any


@app.post("/api/settings")
async def apply_setting(req: SettingRequest):
    if _current_mode is None:
        return {"error": "No active mode"}
    _current_mode.apply_setting(req.key, req.value)
    if _current_mode_id:
        _persist_setting(_current_mode_id, req.key, req.value)
    await ws_manager.broadcast({"type": "settings_changed"})
    return {"ok": True}


@app.post("/api/plugins/reload")
async def reload_plugins():
    plugins.reload()
    return {"ok": True, "modes": list(plugins.modes.keys())}


# ── Display on/off ────────────────────────────────────────────────────────────
@app.get("/api/display/status")
async def display_status():
    return {"on": _display_on}


async def _do_display_off():
    global _display_on
    if _display_on:
        _display_on = False
        frame_sender.send(_BLANK)
        state_sender.send(False)
        await ws_manager.broadcast({"type": "display_state", "on": False})
        print("[main] display OFF")
    return {"ok": True, "display_on": False}


async def _do_display_on():
    global _display_on
    if not _display_on:
        _display_on = True
        state_sender.send(True)
        await ws_manager.broadcast({"type": "display_state", "on": True})
        print("[main] display ON")
    return {"ok": True, "display_on": True}


@app.get("/api/display/off")
@app.post("/api/display/off")
async def display_off():
    return await _do_display_off()


@app.get("/api/display/on")
@app.post("/api/display/on")
async def display_on_endpoint():
    return await _do_display_on()


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _current_brightness
    await ws_manager.connect(websocket)
    await websocket.send_json({
        "type": "state",
        "mode_id": _current_mode_id,
        "brightness": _current_brightness,
        "display_on": _display_on,
        "modes": _mode_list(),
    })
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "gyro":
                if _current_mode is not None:
                    _game_over_timer = 0.0
                    _current_mode.handle_gyro(
                        float(data.get("gamma", 0)),
                        float(data.get("beta",  0)),
                    )

            elif msg_type == "accel":
                if _current_mode is not None:
                    _current_mode.handle_accel(
                        float(data.get("x", 0)),
                        float(data.get("y", 0)),
                        float(data.get("z", 0)),
                    )

            elif msg_type == "input":
                if _current_mode is not None:
                    _game_over_timer = 0.0
                    _current_mode.handle_input(
                        int(data.get("player", 0)),
                        str(data.get("action", "")),
                    )

            elif msg_type == "set_mode":
                ok = _activate_mode(data["mode_id"])
                if ok:
                    await ws_manager.broadcast({
                        "type": "mode_changed",
                        "mode_id": _current_mode_id,
                    })

            elif msg_type == "set_brightness":
                _current_brightness = max(0, min(255, int(data["value"])))
                brightness_sender.send(_current_brightness)
                await ws_manager.broadcast({
                    "type": "brightness",
                    "value": _current_brightness,
                })

            elif msg_type == "apply_setting":
                if _current_mode is not None:
                    key = str(data["key"])
                    val = data["value"]
                    _current_mode.apply_setting(key, val)
                    if _current_mode_id:
                        _persist_setting(_current_mode_id, key, val)
                    await ws_manager.broadcast({"type": "settings_changed"})

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio as _asyncio
    import uvicorn

    _host      = _cfg["server"].get("host", "0.0.0.0")
    _http_port = _cfg["server"].get("port", 8080)
    _ssl_key   = _ROOT / "key.pem"
    _ssl_cert  = _ROOT / "cert.pem"
    _has_ssl   = _ssl_key.exists() and _ssl_cert.exists()

    async def _serve():
        # HTTP on 8080 — primary server, runs full lifespan (game loop etc.)
        http_cfg = uvicorn.Config(app, host=_host, port=_http_port,
                                  reload=False, lifespan="on")
        http_srv = uvicorn.Server(http_cfg)

        if _has_ssl:
            print(f"[main] HTTP on :{_http_port}  |  HTTPS on :8443")
            # HTTPS on 8443 — shares same app object, lifespan already running
            https_cfg = uvicorn.Config(app, host=_host, port=8443,
                                       ssl_keyfile=str(_ssl_key),
                                       ssl_certfile=str(_ssl_cert),
                                       lifespan="off")
            https_srv = uvicorn.Server(https_cfg)
            await _asyncio.gather(http_srv.serve(), https_srv.serve())
        else:
            print(f"[main] HTTP on :{_http_port} (no cert.pem found, HTTPS disabled)")
            await http_srv.serve()

    _asyncio.run(_serve())
