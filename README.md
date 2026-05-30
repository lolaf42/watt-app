# Watt — Battery Monitor

Cross-platform system tray battery monitor for **Windows 10/11** and **Ubuntu 24.04 LTS** (including VMs).

## Features

- System tray icon with color-coded battery level (green/yellow/red)
- Click tray icon → compact popup with full battery details
- Configurable percentage alerts (low + high thresholds)
- Charger plug/unplug notifications
- Battery health %, cycle count, temperature, voltage, current
- Persistent settings (JSON config)
- Autostart on login (optional)

---

## Installation

### Ubuntu 24.04 LTS

```bash
# System dependencies (AppIndicator tray support)
sudo apt install python3-pip python3-tk libayatana-appindicator3-1 \
     gir1.2-ayatanaappindicator3-0.1 libnotify-bin

# Python dependencies
cd watt-app
pip install -r requirements.txt

# Run
python3 main.py &
```

> **If gir1.2-ayatanaappindicator3 is not available**, try the older package:
> ```bash
> sudo apt install gir1.2-appindicator3-0.1
> ```

### Windows 10/11

```bat
pip install -r requirements.txt winotify
python main.py
```

---

## VM-specific Notes (Ubuntu in VirtualBox / VMware)

- Battery data is read directly from `/sys/class/power_supply/` via the kernel ACPI interface — this works in VMs that expose a virtual battery (most do via ACPI).
- **VirtualBox**: Enable ACPI in VM settings → System → Enable ACPI.
- **VMware**: ACPI is enabled by default. Virtual battery appears as `BAT0`.
- If no battery is detected, the tray shows "No battery detected" and alerts are silenced — the app still runs without error.
- UPower D-Bus is NOT required (unreliable in VMs). Direct `/sys` reads are used instead.

---

## Building a Standalone Binary

### Linux
```bash
chmod +x build_linux.sh
./build_linux.sh
# Output: dist/watt
```

### Windows
```bat
build_windows.bat
REM Output: dist\watt.exe
```

---

## Config File

Stored at:
- **Linux**: `~/.config/watt-app/config.json`
- **Windows**: `%APPDATA%\watt-app\config.json`

```json
{
  "poll_interval": 30,
  "thresholds": {
    "low": [5, 10, 20],
    "high": [80]
  },
  "alerts": {
    "plugged": true,
    "unplugged": true,
    "threshold_low": true,
    "threshold_high": true
  },
  "autostart": false
}
```

---

## Manual Autostart (Fallback)

### Linux
```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/watt-app.desktop << EOF
[Desktop Entry]
Type=Application
Name=Watt Battery Monitor
Exec=/usr/local/bin/watt
Hidden=false
X-GNOME-Autostart-enabled=true
EOF
```

### Windows
Add `watt.exe` to:
```
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
```
Value name: `watt-app`, Value: full path to `watt.exe`

---

## Dependencies

| Package | Purpose |
|---------|---------|
| pystray | Cross-platform system tray |
| Pillow | Dynamic tray icon generation |
| psutil | Battery data (fallback + Windows) |
| plyer | Notification fallback |
| winotify | Windows 10/11 toast notifications |
| tkinter | Settings + popup UI (stdlib) |
