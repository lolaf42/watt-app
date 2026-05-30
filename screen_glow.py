"""Screen glow launcher — manages the glow_worker.py subprocess.

show()  → starts the GTK3/Cairo glow border (idempotent, restarts on colour change)
hide()  → terminates it

The worker process runs for as long as the condition (charging / critical) is active.
"""

import os
import subprocess
import sys
import tkinter as tk
from typing import Optional

_WORKER = os.path.join(os.path.dirname(__file__), "glow_worker.py")


class ScreenGlow:

    def __init__(self, root: tk.Tk):
        self._root  = root
        self._proc: Optional[subprocess.Popen] = None
        self._color: Optional[tuple]            = None

    # ── Public (thread-safe via root.after) ───────────────────────────────────

    def show(self, color: tuple) -> None:
        self._root.after(0, lambda: self._start(color))

    def hide(self) -> None:
        self._root.after(0, self._stop)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _start(self, color: tuple) -> None:
        # Already running with the same color — nothing to do
        if self._proc and self._proc.poll() is None and self._color == color:
            return
        self._stop()
        r, g, b = color
        try:
            self._proc = subprocess.Popen(
                [sys.executable, _WORKER, str(r), str(g), str(b)],
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
