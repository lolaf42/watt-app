"""Autostart on login — Windows registry / Linux .desktop file."""

import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
APP_NAME = "watt-app"


def set_autostart(enabled: bool) -> None:
    exe = _get_exec_cmd()
    if sys.platform == "win32":
        _windows(enabled, exe)
    else:
        _linux(enabled, exe)


def _get_exec_cmd() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{script}"'


def _windows(enabled: bool, cmd: str) -> None:
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                             winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Autostart (Windows) failed: {e}")


def _linux(enabled: bool, cmd: str) -> None:
    autostart_dir = Path.home() / ".config" / "autostart"
    desktop = autostart_dir / f"{APP_NAME}.desktop"

    if enabled:
        autostart_dir.mkdir(parents=True, exist_ok=True)
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Watt Battery Monitor\n"
            f"Exec={cmd}\n"
            "Hidden=false\n"
            "NoDisplay=false\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Comment=System tray battery monitor\n"
        )
        desktop.chmod(0o755)
    else:
        desktop.unlink(missing_ok=True)
