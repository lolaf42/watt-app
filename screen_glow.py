"""Screen glow launcher — manages the glow_worker.py subprocess."""

import os
import subprocess
import sys
import tkinter as tk
from typing import Optional

_WORKER = os.path.join(os.path.dirname(__file__), "glow_worker.py")


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
        gc = self._config.data.get("glow", {}) if self._config else {}
        speed  = int(gc.get("snake_speed",       600))
        lw     = int(gc.get("line_width",           4))
        bint   = int(gc.get("border_intensity",   100))
        bdur   = float(gc.get("border_duration",  1.5))
        return [sys.executable, _WORKER,
                str(r), str(g), str(b),
                str(speed), str(lw), str(bint), str(bdur)]

    def _start(self, color: tuple) -> None:
        if self._proc and self._proc.poll() is None and self._color == color:
            return
        self._stop()
        try:
            self._proc = subprocess.Popen(
                self._glow_args(color),
                stdout=subprocess.DEVNULL,
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
