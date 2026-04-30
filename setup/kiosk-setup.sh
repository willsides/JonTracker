#!/bin/bash
# Run this script on the Pi after first boot to configure kiosk mode.
# Usage: bash kiosk-setup.sh
# The Pi must be connected to the internet.

set -e

KIOSK_URL="https://jontracker.willsides.me"
USER="${SUDO_USER:-pi}"
HOME_DIR="/home/$USER"

echo "=== JonTracker Kiosk Setup ==="
echo "Kiosk URL: $KIOSK_URL"
echo "User: $USER"
echo

# --- Install dependencies ---
echo "[1/5] Installing packages..."
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
    chromium \
    unclutter \
    xdotool

# --- Switch to X11 if currently using Wayland ---
# X11 is more compatible with kiosk mode flags
echo "[2/5] Ensuring X11 display server..."
if grep -q "wayland" /etc/systemd/system/display-manager.service 2>/dev/null || \
   raspi-config nonint get_wm 2>/dev/null | grep -qi wayland; then
    echo "  Switching from Wayland to X11..."
    sudo raspi-config nonint do_wayland W1  # W1 = X11
fi

# --- Disable screen blanking at system level ---
echo "[3/5] Disabling screen blanking and DPMS..."
sudo mkdir -p /etc/X11/xorg.conf.d
sudo tee /etc/X11/xorg.conf.d/10-blanking.conf > /dev/null << 'EOF'
Section "ServerFlags"
    Option "BlankTime"   "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime"     "0"
EndSection
EOF

# --- Configure LXDE autostart for kiosk ---
echo "[4/5] Configuring kiosk autostart..."
mkdir -p "$HOME_DIR/.config/lxsession/LXDE-pi"

cat > "$HOME_DIR/.config/lxsession/LXDE-pi/autostart" << AUTOSTART
# Disable screensaver and power management
@xset s off
@xset -dpms
@xset s noblank

# Hide mouse cursor after 0.5s of inactivity
@unclutter -idle 0.5 -root

# Launch Chromium in kiosk mode
@chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --disable-features=TranslateUI \
  --no-default-browser-check \
  --check-for-update-interval=31536000 \
  --disable-pinch \
  $KIOSK_URL
AUTOSTART

chown -R "$USER:$USER" "$HOME_DIR/.config"

# --- Configure auto-login ---
echo "[5/5] Configuring auto-login..."
sudo raspi-config nonint do_boot_behaviour B4  # B4 = Desktop auto-login

echo
echo "=== Setup complete ==="
echo "To exit kiosk and configure WiFi:"
echo "  1. Plug in keyboard + mouse"
echo "  2. Press Ctrl+Alt+T to open a terminal (configured below)"
echo "  3. Use 'nm-connection-editor' or the taskbar WiFi icon to add networks"
echo
echo "Rebooting in 5 seconds... (Ctrl+C to cancel)"
sleep 5
sudo reboot
