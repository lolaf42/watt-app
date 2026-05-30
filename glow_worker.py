#!/usr/bin/env python3
"""GTK3/Cairo persistent glow border — runs while charging.

Draws a wide, breathing green glow frame around all 4 screen edges,
with RGBA transparency so the desktop stays fully visible.

Usage: python3 glow_worker.py <r> <g> <b>
Runs until terminated by the parent (screen_glow.py).
"""

import os
os.environ.setdefault("GDK_BACKEND", "x11")   # must be before gi import

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import cairo
import math
import sys
import time

# ── Colour from CLI args ──────────────────────────────────────────────────────
_R, _G, _B = int(sys.argv[1]) / 255, int(sys.argv[2]) / 255, int(sys.argv[3]) / 255

_GLOW_W      = 72    # glow width (px) inward from each edge
_PULSE_S     = 3.0   # seconds per breath cycle
_SHOW_S      = 5.0   # seconds to stay fully visible
_FADE_S      = 1.0   # seconds for the fade-out at the end
_FPS         = 30    # frames per second


class GlowBorder:

    def __init__(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        geo     = monitor.get_geometry()
        self.sw, self.sh = geo.width, geo.height
        self._t0 = time.monotonic()

        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_accept_focus(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)

        # ── RGBA visual for per-pixel transparency ────────────────────────────
        screen      = win.get_screen()
        rgba_visual = screen.get_rgba_visual()
        if rgba_visual:
            win.set_visual(rgba_visual)
        win.set_app_paintable(True)

        # ── Size/position ─────────────────────────────────────────────────────
        win.set_default_size(self.sw, self.sh)
        win.resize(self.sw, self.sh)
        win.connect("draw", self._on_draw)
        win.show_all()
        win.move(geo.x, geo.y)
        win.resize(self.sw, self.sh)

        # ── Click-through: empty input region (after show_all) ────────────────
        win.input_shape_combine_region(cairo.Region())

        self.win = win
        GLib.timeout_add(1000 // _FPS, self._tick)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _tick(self) -> bool:
        age = time.monotonic() - self._t0
        if age >= _SHOW_S + _FADE_S:
            Gtk.main_quit()
            return False
        self.win.queue_draw()
        return True

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _on_draw(self, widget, cr: cairo.Context) -> bool:
        W, H = self.sw, self.sh
        gw   = _GLOW_W
        r, g, b = _R, _G, _B

        # Fully transparent base
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Breathing pulse + fade-out after _SHOW_S seconds
        age = time.monotonic() - self._t0
        if age >= _SHOW_S:
            # Smooth fade-out over _FADE_S seconds
            fade  = max(0.0, 1.0 - (age - _SHOW_S) / _FADE_S)
            pulse = fade
        else:
            # Gentle breathing (±15 %)
            pulse = 0.85 + 0.15 * math.cos(age * 2 * math.pi / _PULSE_S)

        def _grad(gx0, gy0, gx1, gy1):
            """Linear gradient from screen edge (bright) to interior (clear)."""
            pat = cairo.LinearGradient(gx0, gy0, gx1, gy1)
            pat.add_color_stop_rgba(0.00, r, g, b, pulse * 1.00)
            pat.add_color_stop_rgba(0.15, r, g, b, pulse * 0.90)
            pat.add_color_stop_rgba(0.35, r, g, b, pulse * 0.55)
            pat.add_color_stop_rgba(0.60, r, g, b, pulse * 0.18)
            pat.add_color_stop_rgba(0.80, r, g, b, pulse * 0.05)
            pat.add_color_stop_rgba(1.00, r, g, b, 0.00)
            return pat

        # Top  — gradient flows downward from y=0
        cr.set_source(_grad(0, 0,   0, gw))
        cr.rectangle(0,    0,    W,  gw)
        cr.fill()

        # Bottom — gradient flows upward from y=H
        cr.set_source(_grad(0, H,   0, H - gw))
        cr.rectangle(0,    H-gw, W,  gw)
        cr.fill()

        # Left  — gradient flows rightward from x=0
        cr.set_source(_grad(0, 0,   gw, 0))
        cr.rectangle(0,    0,    gw, H)
        cr.fill()

        # Right — gradient flows leftward from x=W
        cr.set_source(_grad(W, 0,   W-gw, 0))
        cr.rectangle(W-gw, 0,    gw, H)
        cr.fill()

        return False


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    GlowBorder()
    Gtk.main()
