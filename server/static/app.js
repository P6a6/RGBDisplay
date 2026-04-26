'use strict';

// Prevent double-tap zoom and long-press context menu globally
document.addEventListener('contextmenu', e => e.preventDefault());
document.addEventListener('gesturestart',  e => e.preventDefault());
document.addEventListener('gesturechange', e => e.preventDefault());
document.addEventListener('gestureend',    e => e.preventDefault());

// Block double-tap zoom on iOS (most reliable method)
let _lastTap = 0;
document.addEventListener('touchend', e => {
  const now = Date.now();
  if (now - _lastTap < 300) {
    e.preventDefault();
  }
  _lastTap = now;
}, { passive: false });

// ── State ─────────────────────────────────────────────────────────────────
const state = {
  modeId:     null,
  brightness: 128,
  displayOn:  true,
  modes:      [],
  player:     0,
};

// ── DOM refs ──────────────────────────────────────────────────────────────
const dot            = document.getElementById('dot');
const goGyroBtn      = document.getElementById('go-gyro');
const brightnessEl   = document.getElementById('brightness');
const brightnessVal  = document.getElementById('brightness-val');
const modesContainer = document.getElementById('modes-container');
const settingsPanel  = document.getElementById('settings-panel');
const settingsTitle  = document.getElementById('settings-title');
const settingsContent= document.getElementById('settings-content');
const ctrlNotice     = document.getElementById('ctrl-notice');
const powerBtn       = document.getElementById('power-btn');
const gameOverlay    = document.getElementById('game-overlay');
const goTitle        = document.getElementById('go-title');
const goExit         = document.getElementById('go-exit');

// ── WebSocket ─────────────────────────────────────────────────────────────
let ws = null;
let reconnectTimer = null;

function wsConnect() {
  const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
  ws = new WebSocket(url);

  ws.onopen = () => {
    dot.classList.add('ok');
    clearTimeout(reconnectTimer);
  };

  ws.onclose = () => {
    dot.classList.remove('ok');
    reconnectTimer = setTimeout(wsConnect, 2500);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = (ev) => {
    try { handleMsg(JSON.parse(ev.data)); } catch (e) { /* ignore */ }
  };
}

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

function handleMsg(msg) {
  switch (msg.type) {
    case 'state':
      state.modeId     = msg.mode_id;
      state.brightness = msg.brightness;
      state.modes      = msg.modes || [];
      setDisplayOn(msg.display_on !== false, false);
      setBrightness(msg.brightness, false);
      renderModes();
      refreshSettings();
      break;

    case 'mode_changed':
      state.modeId = msg.mode_id;
      renderModes();
      refreshSettings();
      updateCtrlNotice();
      break;

    case 'brightness':
      setBrightness(msg.value, false);
      break;

    case 'settings_changed':
      refreshSettings();
      break;

    case 'display_state':
      setDisplayOn(msg.on, false);
      break;
  }
}

// ── Brightness ────────────────────────────────────────────────────────────
let brightnessSendTimer = null;

function setBrightness(v, send = true) {
  state.brightness = v;
  brightnessEl.value = v;
  brightnessVal.textContent = v;
  if (send) {
    clearTimeout(brightnessSendTimer);
    brightnessSendTimer = setTimeout(() => {
      wsSend({ type: 'set_brightness', value: v });
    }, 60);
  }
}

brightnessEl.addEventListener('input', () => {
  setBrightness(parseInt(brightnessEl.value, 10), true);
});

// ── Display on/off ────────────────────────────────────────────────────────
function setDisplayOn(on, send = true) {
  state.displayOn = on;
  powerBtn.textContent = on ? 'Display On' : 'Display Off';
  powerBtn.className = 'power-btn ' + (on ? 'power-on' : 'power-off');
  modesContainer.classList.toggle('dimmed', !on);
  settingsPanel.classList.toggle('dimmed', !on);
  if (send) {
    fetch(`/api/display/${on ? 'on' : 'off'}`, { method: 'POST' }).catch(() => {});
  }
}

powerBtn.addEventListener('click', () => setDisplayOn(!state.displayOn, true));

// ── Tabs ──────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(tab.dataset.view).classList.add('active');
    if (tab.dataset.view === 'view-controller') updateCtrlNotice();
  });
});

// ── Game overlay ──────────────────────────────────────────────────────────
let goPlayer = 0;

function openGameOverlay(mode) {
  goTitle.textContent = mode.name;
  gameOverlay.hidden = false;
  // Request fullscreen + landscape lock for the best controller experience
  try { document.documentElement.requestFullscreen(); } catch(_) {}
  try { screen.orientation.lock('landscape'); } catch(_) {}
}

function closeGameOverlay() {
  stopGyro();
  gameOverlay.hidden = true;
  try { document.exitFullscreen(); } catch(_) {}
  try { screen.orientation.unlock(); } catch(_) {}
  wsSend({ type: 'set_mode', mode_id: null });
}

goExit.addEventListener('click', closeGameOverlay);

// ── Gyroscope ─────────────────────────────────────────────────────────────
let gyroActive   = false;
let gyroInterval = null;
let gyroGamma    = 0;
let gyroBeta     = 0;
let accelX = 0, accelY = 0, accelZ = 0;

function onDeviceOrientation(e) {
  gyroGamma = e.gamma ?? 0;
  gyroBeta  = e.beta  ?? 0;
}

function onDeviceMotion(e) {
  // Use linear acceleration (gravity removed) for intentional movement detection
  const a = e.acceleration || e.accelerationIncludingGravity;
  if (a) {
    accelX = a.x ?? 0;
    accelY = a.y ?? 0;
    accelZ = a.z ?? 0;
  }
}

function startGyro() {
  window.addEventListener('deviceorientation', onDeviceOrientation);
  window.addEventListener('devicemotion',      onDeviceMotion);
  gyroInterval = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'gyro',  gamma: gyroGamma, beta: gyroBeta }));
      ws.send(JSON.stringify({ type: 'accel', x: accelX, y: accelY, z: accelZ }));
    }
    const mag = Math.sqrt(accelX*accelX + accelY*accelY + accelZ*accelZ);
    const arrow = accelY > 1.5 ? '▲' : accelY < -1.5 ? '▼' : '●';
    goGyroBtn.textContent = `${arrow} ${mag.toFixed(1)}`;
  }, 33); // ~30 fps
  gyroActive = true;
  goGyroBtn.classList.add('active');
  goGyroBtn.textContent = 'GYRO ON';
}

function stopGyro() {
  window.removeEventListener('deviceorientation', onDeviceOrientation);
  window.removeEventListener('devicemotion',      onDeviceMotion);
  if (gyroInterval) { clearInterval(gyroInterval); gyroInterval = null; }
  gyroActive = false;
  goGyroBtn.classList.remove('active');
  goGyroBtn.textContent = 'GYRO';
}

goGyroBtn.addEventListener('click', async () => {
  if (gyroActive) { stopGyro(); return; }
  if (location.protocol !== 'https:') {
    alert('Motion sensors require HTTPS.\n\nOpen: https://' + location.hostname + ':8443');
    return;
  }
  // iOS 13+ needs explicit permission for both orientation AND motion
  try {
    if (typeof DeviceOrientationEvent?.requestPermission === 'function') {
      const r = await DeviceOrientationEvent.requestPermission();
      if (r !== 'granted') { alert('Orientation permission denied.'); return; }
    }
    if (typeof DeviceMotionEvent?.requestPermission === 'function') {
      const r = await DeviceMotionEvent.requestPermission();
      if (r !== 'granted') { alert('Motion permission denied.'); return; }
    }
  } catch (e) { alert('Sensor permission error: ' + e); return; }
  startGyro();
});

// Player toggle inside overlay
document.querySelectorAll('.go-player-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    goPlayer = parseInt(btn.dataset.goplayer, 10);
    document.querySelectorAll('.go-player-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

// Wire all overlay action buttons (d-pad + face + menu)
// Directional buttons auto-repeat while held so games like Pong work smoothly.
function _wireOverlayBtn(btn) {
  const action = btn.dataset.action;
  const isDir  = ['up', 'down', 'left', 'right'].includes(action);
  let repeatId = null;

  function send() { wsSend({ type: 'input', player: goPlayer, action }); }

  function stopRepeat() {
    btn.classList.remove('pressed');
    if (repeatId) { clearInterval(repeatId); repeatId = null; }
  }

  btn.addEventListener('pointerdown', e => {
    e.preventDefault();
    btn.classList.add('pressed');
    send();
    if (isDir) repeatId = setInterval(send, 60);
  });
  btn.addEventListener('pointerup',     stopRepeat);
  btn.addEventListener('pointercancel', stopRepeat);
  btn.addEventListener('pointerleave',  stopRepeat);
}
document.querySelectorAll(
  '.go-dpad-btn[data-action], .go-face-btn[data-action], .go-menu-btn[data-action]'
).forEach(_wireOverlayBtn);

// ── Modes grid ────────────────────────────────────────────────────────────
function renderModes() {
  const byCategory = {};
  state.modes.forEach(m => {
    const cat = m.category || 'other';
    (byCategory[cat] = byCategory[cat] || []).push(m);
  });

  modesContainer.innerHTML = '';
  const catOrder = ['ambient', 'music', 'games'];
  const allCats  = [...new Set([...catOrder, ...Object.keys(byCategory)])];
  allCats.forEach(cat => {
    const list = byCategory[cat];
    if (!list || !list.length) return;

    const label = document.createElement('div');
    label.className = 'section-label';
    label.textContent = cat;
    modesContainer.appendChild(label);

    const grid = document.createElement('div');
    grid.className = 'modes-grid';
    list.forEach(mode => {
      const card = document.createElement('div');
      card.className = 'mode-card' + (mode.id === state.modeId ? ' active' : '');
      card.innerHTML = `
        <div class="name">${escHtml(mode.name)}</div>
        <div class="desc">${escHtml(mode.description || '')}</div>
        <span class="badge ${escHtml(cat)}">${escHtml(cat)}</span>
      `;
      card.addEventListener('click', () => {
        wsSend({ type: 'set_mode', mode_id: mode.id });
        // Games auto-launch the full-screen controller
        if (cat === 'games') openGameOverlay(mode);
      });
      grid.appendChild(card);
    });
    modesContainer.appendChild(grid);
  });
}

// ── Settings panel ────────────────────────────────────────────────────────
async function refreshSettings() {
  if (!state.modeId) { settingsPanel.hidden = true; return; }

  let settings;
  try {
    const r = await fetch('/api/settings');
    settings = await r.json();
  } catch { return; }

  if (!Array.isArray(settings) || !settings.length) {
    settingsPanel.hidden = true;
    return;
  }

  settingsPanel.hidden = false;
  const mode = state.modes.find(m => m.id === state.modeId);
  settingsTitle.textContent = (mode ? mode.name + ' ' : '') + 'Settings';
  settingsContent.innerHTML = '';

  settings.forEach(s => {
    const row   = document.createElement('div');
    row.className = 'setting-row';

    const lbl = document.createElement('label');
    lbl.className = 'setting-label';
    lbl.textContent = s.label;
    row.appendChild(lbl);

    if (s.type === 'range') {
      const inp = document.createElement('input');
      inp.type = 'range';
      inp.min = s.min; inp.max = s.max; inp.step = s.step; inp.value = s.value;

      const num = document.createElement('span');
      num.className = 'setting-num';
      num.textContent = s.value;

      let t = null;
      inp.addEventListener('input', () => {
        num.textContent = inp.value;
        clearTimeout(t);
        t = setTimeout(() => sendSetting(s.key, parseFloat(inp.value)), 100);
      });
      row.appendChild(inp);
      row.appendChild(num);

    } else if (s.type === 'color') {
      const inp = document.createElement('input');
      inp.type = 'color';
      inp.value = s.value;
      let t = null;
      inp.addEventListener('input', () => {
        clearTimeout(t);
        t = setTimeout(() => sendSetting(s.key, inp.value), 100);
      });
      row.appendChild(inp);

    } else if (s.type === 'select') {
      const sel = document.createElement('select');
      (s.options || []).forEach(opt => {
        const o = document.createElement('option');
        o.value = opt.value;
        o.textContent = opt.label;
        if (String(opt.value) === String(s.value)) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener('change', () => sendSetting(s.key, sel.value));
      row.appendChild(sel);
    }

    settingsContent.appendChild(row);
  });
}

function sendSetting(key, value) {
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, value }),
  }).catch(() => {});
}

// ── Controller ────────────────────────────────────────────────────────────
document.querySelectorAll('.player-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    state.player = parseInt(btn.dataset.player, 10);
    document.querySelectorAll('.player-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  });
});

function sendInput(action) {
  wsSend({ type: 'input', player: state.player, action });
}

// Touch + mouse for all controller buttons
document.querySelectorAll(
  '.dpad-btn[data-action], .face-btn[data-action], .menu-btn[data-action]'
).forEach(btn => {
  const action = btn.dataset.action;

  btn.addEventListener('pointerdown', e => {
    e.preventDefault();
    btn.classList.add('pressed');
    sendInput(action);
  });
  btn.addEventListener('pointerup',    () => btn.classList.remove('pressed'));
  btn.addEventListener('pointercancel',() => btn.classList.remove('pressed'));
  btn.addEventListener('pointerleave', () => btn.classList.remove('pressed'));
});

// Keyboard — arrows = P1 (or active player), WASD = opposite player
const KEY_MAP = {
  ArrowUp:    { dir: 'up'    },
  ArrowDown:  { dir: 'down'  },
  ArrowLeft:  { dir: 'left'  },
  ArrowRight: { dir: 'right' },
  w: { dir: 'up'    },
  s: { dir: 'down'  },
  a: { dir: 'left'  },
  d: { dir: 'right' },
  Enter: { action: 'start'  },
  ' ':   { action: 'select' },
};

document.addEventListener('keydown', e => {
  const map = KEY_MAP[e.key];
  if (!map) return;
  e.preventDefault();
  const action = map.dir || map.action;
  // Arrow keys → P1 always; WASD → P2 always; Enter/Space → active player
  let player = state.player;
  if (['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)) player = 0;
  if (['w','a','s','d'].includes(e.key)) player = 1;
  wsSend({ type: 'input', player, action });
});

// ── Controller notice ─────────────────────────────────────────────────────
function updateCtrlNotice() {
  if (!state.modeId) {
    ctrlNotice.textContent = 'No mode active — pick one in the Control tab first.';
  } else {
    const mode = state.modes.find(m => m.id === state.modeId);
    ctrlNotice.textContent = mode ? `Active: ${mode.name}` : '';
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── HTTP state fetch (boot + polling fallback) ────────────────────────────
async function fetchState() {
  try {
    const [modesRes, stateRes] = await Promise.all([
      fetch('/api/modes'),
      fetch('/api/state'),
    ]);
    if (!modesRes.ok || !stateRes.ok) return;
    const modes = await modesRes.json();
    const st    = await stateRes.json();
    state.modes      = Array.isArray(modes) ? modes : [];
    state.modeId     = st.mode_id ?? null;
    state.brightness = st.brightness ?? 128;
    setDisplayOn(st.display_on !== false, false);
    setBrightness(state.brightness, false);
    renderModes();
    refreshSettings();
  } catch (e) { /* ignore */ }
}

// Poll every 3 seconds when WS is disconnected so the UI stays functional
let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  fetchState();
  pollTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) fetchState();
    else { clearInterval(pollTimer); pollTimer = null; }
  }, 3000);
}

// ── Boot ──────────────────────────────────────────────────────────────────
fetchState();
wsConnect();
// Start polling — stops itself once WS comes up
setTimeout(startPolling, 1000);
