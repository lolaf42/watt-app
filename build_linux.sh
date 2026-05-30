#!/usr/bin/env bash
# Build Watt as a standalone Linux binary using PyInstaller
set -e

echo "Installing dependencies..."
pip install -r requirements.txt pyinstaller

echo "Building binary..."
pyinstaller \
  --onefile \
  --noconsole \
  --name watt \
  --add-data "assets:assets" \
  --hidden-import pystray._xorg \
  --hidden-import pystray._appindicator \
  main.py

echo ""
echo "Done! Binary at: dist/watt"
echo ""
echo "To install system-wide:"
echo "  sudo cp dist/watt /usr/local/bin/watt"
echo "  watt &"
