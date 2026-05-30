"""Screen glow launcher — manages the glow_worker.py subprocess."""

import os
import subprocess
import sys
import tkinter as tk
from typing import Optional

_WORKER = os.path.join(os.path.dirname(__file__), "glow_worker.py")


def _clean_env() -> dict:
    env = os.environ.copy()
    # Strip snap-injected GTK/GDK vars that cause libpthread conflicts when
    # VS Code (itself a snap) passes its own GTK paths to subprocesses.
    _SNAP_VARS = {
        "GTK_PATH", "GTK_EXE_PREFIX", "GTK_IM_MODULE_FILE",
        "GDK_PIXBUF_MODULE_FILE", "GDK_PIXBUF_MODULEDIR",
        "GIO_MODULE_DIR", "GSETTINGS_SCHEMA_DIR",
        "SNAP_LIBRARY_PATH",
    }
    for k in _SNAP_VARS:
        env.pop(k, None)
    for k in list(env):
        if env[k] and "/snap/" in env[k] and k in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            env.pop(k, None)
    return env


class ScreenGlow:

    def __init__(self, root: tk.Tk, config=None):
        self._root   = root
        self._config = config
        self._proc:  Optional[subprocess.Popen] = None
        self._color: Optional[tuple]             = None

    # ── Public (thread-safe via root.after) ───────────────────────────────────

    def show(self, color: tuple) -> None:
        self._root.after(0, lambda: self._start(color))

    def hide(self) -> None:
        self._root.after(0, self._stop)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _glow_args(self, color: tuple) -> list:
        r, g, b = color
        gc   = self._config.data.get("glow", {}) if self._config else {}
        bint = int(gc.get("border_intensity", 100))
        bdur = float(gc.get("border_duration", 3.0))
        return [sys.executable, _WORKER,
                str(r), str(g), str(b), str(bint), str(bdur)]

    def preview(self, glow_cfg: dict) -> None:
        """Force-restart with temporary config for live settings preview."""
        self._root.after(0, lambda: self._preview(glow_cfg))

    def _preview(self, glow_cfg: dict) -> None:
        self._stop()
        color = (0, 170, 0)
        r, g, b = color
        gc = glow_cfg
        try:
            bint = int(gc.get("border_intensity", 100))
            bdur = float(gc.get("border_duration", 3.0))
            self._proc = subprocess.Popen(
                [sys.executable, _WORKER,
                 str(r), str(g), str(b), str(bint), str(bdur)],
                stdout=subprocess.DEVNULL,
                env=_clean_env(),
            )
            self._color = color
        except Exception:
            pass

    def _start(self, color: tuple) -> None:
        if self._proc and self._proc.poll() is None and self._color == color:
            return
        self._stop()
        try:
            self._proc = subprocess.Popen(
                self._glow_args(color),
                stdout=subprocess.DEVNULL,
                env=_clean_env(),
            )
            self._color = color
        except Exception:
            pass

    def _stop(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        self._color = None
