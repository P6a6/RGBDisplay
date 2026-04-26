#!/usr/bin/env bash
# setup.sh — install the RGB Display server on Ubuntu
# Run from inside the server/ directory, or from anywhere with SERVER_DIR set.
#
# What this does:
#   1. Creates a Python venv at server/venv/
#   2. Installs Python dependencies into the venv
#   3. Creates a dedicated system user 'rgbdisplay'
#   4. Writes /etc/systemd/system/rgbdisplay.service (uses the repo in-place)
#   5. Enables + starts the service
#
# Nothing outside this repo directory is modified except:
#   - /etc/systemd/system/rgbdisplay.service  (new file)
#   - a new 'rgbdisplay' system user is created

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
SERVICE_USER="rgbdisplay"
SERVICE_NAME="rgbdisplay"

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RGB Display Server — setup"
echo "  Repo server dir : $SCRIPT_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# ── Step 1: Python venv ────────────────────────────────────────────────────
echo "[1/4] Python virtual environment"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "      created at $VENV_DIR"
else
    echo "      already exists, skipping create"
fi

echo "      installing / upgrading packages …"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
echo "      done"

# ── Step 2: System user ────────────────────────────────────────────────────
echo
echo "[2/4] System user '$SERVICE_USER'"
if id "$SERVICE_USER" &>/dev/null; then
    echo "      already exists, skipping"
else
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    echo "      created"
fi

# Give the service user read access to the repo
# (We add it to the group that owns the directory rather than chown-ing)
REPO_GROUP=$(stat -c '%G' "$SCRIPT_DIR")
echo "      granting $SERVICE_USER read access via group '$REPO_GROUP'"
sudo usermod -aG "$REPO_GROUP" "$SERVICE_USER" 2>/dev/null || true
# Also make sure the tree is group-readable
chmod -R g+rX "$SCRIPT_DIR"
# The venv must be readable too (pip installed as current user)
chmod -R a+rX "$VENV_DIR"

# ── Step 3: Systemd unit ───────────────────────────────────────────────────
echo
echo "[3/4] Writing systemd service"
UNIT_CONTENT="[Unit]
Description=RGB LED Matrix Display Server
Documentation=file://$SCRIPT_DIR/README.md
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$REPO_GROUP
WorkingDirectory=$SCRIPT_DIR
ExecStart=$VENV_DIR/bin/python main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Basic hardening — keeps the service isolated from other processes
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
"

echo "$UNIT_CONTENT" | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null
sudo systemctl daemon-reload
echo "      written to /etc/systemd/system/${SERVICE_NAME}.service"

# ── Step 4: Enable + start ─────────────────────────────────────────────────
echo
echo "[4/4] Enabling and starting service"
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sleep 1
sudo systemctl status "$SERVICE_NAME" --no-pager -l

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete!"
echo
echo "  Web UI   →  http://$(hostname -I | awk '{print $1}'):8080"
echo
echo "  Useful commands:"
echo "    sudo systemctl status $SERVICE_NAME"
echo "    sudo systemctl restart $SERVICE_NAME"
echo "    journalctl -u $SERVICE_NAME -f"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
