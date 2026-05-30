@echo off
REM Build Watt as a standalone Windows .exe using PyInstaller

echo Installing dependencies...
pip install -r requirements.txt pyinstaller winotify

echo Building .exe...
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name watt ^
  --add-data "assets;assets" ^
  --hidden-import pystray._win32 ^
  main.py

echo.
echo Done! Binary at: dist\watt.exe
echo Run it directly or copy to a permanent location and add to autostart via Settings.
