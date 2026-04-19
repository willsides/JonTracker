#!/usr/bin/env bash
# JonTracker install script for Raspberry Pi OS (Bookworm, Pi 5)
# Run as: bash install.sh
set -e

INSTALL_DIR="/home/pi/jontracker"
SERVICE_USER="pi"

echo "=== JonTracker Installer ==="

# ── 1. Copy files ────────────────────────────────────────────────────────────
echo "[1/6] Copying files to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r . "$INSTALL_DIR/"
sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ── 2. Python venv + deps ────────────────────────────────────────────────────
echo "[2/6] Creating Python virtual environment..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
echo "  Dependencies installed."

# ── 3. Config file ───────────────────────────────────────────────────────────
echo "[3/6] Setting up config..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  echo ""
  echo "  !! ACTION REQUIRED: Edit $INSTALL_DIR/.env with your settings:"
  echo "     - MAPSHARE_ID    (from Garmin Explore app → MapShare)"
  echo "     - EMAIL_ADDRESS  (dedicated Gmail for receiving photos)"
  echo "     - EMAIL_APP_PASSWORD (Gmail App Password, NOT your login password)"
  echo ""
else
  echo "  .env already exists, skipping."
fi

# ── 4. Photos directory ──────────────────────────────────────────────────────
echo "[4/6] Creating photos directory..."
sudo -u "$SERVICE_USER" mkdir -p "$INSTALL_DIR/static/photos"

# ── 5. Systemd services ──────────────────────────────────────────────────────
echo "[5/6] Installing systemd services..."
sudo cp "$INSTALL_DIR/setup/jontracker.service" /etc/systemd/system/
sudo cp "$INSTALL_DIR/setup/kiosk.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable jontracker.service
sudo systemctl enable kiosk.service
echo "  Services enabled."

# ── 6. Chromium check ────────────────────────────────────────────────────────
echo "[6/6] Checking for Chromium..."
if ! command -v chromium-browser &>/dev/null; then
  echo "  Installing Chromium..."
  sudo apt-get install -y chromium-browser
else
  echo "  Chromium already installed."
fi

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/.env with your MapShare ID and Gmail credentials"
echo "  2. Start the services:"
echo "       sudo systemctl start jontracker"
echo "       sudo systemctl start kiosk"
echo "  3. Check logs if something looks wrong:"
echo "       sudo journalctl -u jontracker -f"
echo "       sudo journalctl -u kiosk -f"
echo ""
echo "The display will auto-start on reboot."
