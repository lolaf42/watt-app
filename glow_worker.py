#!/usr/bin/env python3
"""GTK3/Cairo growing-snake glow animation.

A bright green line starts at left-center and grows clockwise:
  left-center → up → top-right → down → bottom-left → back to start

On completion: one breath flash, then fades out and exits.

Usage: python3 glow_worker.py <r> <g> <b>
"""

import os
os.environ.setdefault("GDK_BACKEND", "x11")

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import cairo
import math
import sys
import time

# ── Colour ────────────────────────────────────────────────────────────────────
_R, _G, _B = int(sys.argv[1]) / 255, int(sys.argv[2]) / 255, int(sys.argv[3]) / 255

# ── Timing ────────────────────────────────────────────────────────────────────
_SPEED   = 1400   # px / second the head travels
_FINISH_S = 1.2   # seconds to breathe + fade after loop completes
_FPS     = 60

# ── Glow layers: (line_width_px, alpha) outer → inner ────────────────────────
_LAYERS = [(26, 0.07), (12, 0.35), (5, 1.00)]


def _xy(d: float, perim: float, W: int, H: int):
    """Clockwise perimeter distance from top-left → screen (x, y)."""
    d = d % perim
    if d < W:     return d,     0.0
    d -= W
    if d < H:     return W,     d
    d -= H
    if d < W:     return W - d, H
    d -= W
    return            0.0,  H - d


class GlowSnake:

    _GROWING = "growing"
    _FINISH  = "finish"

    def __init__(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        geo     = monitor.get_geometry()
        self.sw, self.sh = geo.width, geo.height

        self.perim   = 2 * (self.sw + self.sh)
        # Left-center going upward in the clockwise parameterisation
        self.start_d = float(2 * self.sw + (self.sh * 3) // 2)

        self.elapsed  = 0.0
        self.last_t   = time.monotonic()
        self.phase    = self._GROWING
        self.phase_t  = 0.0

        # ── GTK window ────────────────────────────────────────────────────────
        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_accept_focus(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)

        screen = win.get_screen()
        rgba   = screen.get_rgba_visual()
        if rgba:
            win.set_visual(rgba)
        win.set_app_paintable(True)

        win.set_default_size(self.sw, self.sh)
        win.resize(self.sw, self.sh)
        win.connect("draw", self._on_draw)
        win.show_all()
        win.move(geo.x, geo.y)
        win.resize(self.sw, self.sh)
        win.input_shape_combine_region(cairo.Region())

        self.win = win
        GLib.timeout_add(1000 // _FPS, self._tick)

    # ── Loop ──────────────────────────────────────────────────────────────────

    def _tick(self) -> bool:
        now = time.monotonic()
        dt  = now - self.last_t
        self.last_t = now

        if self.phase == self._GROWING:
            self.elapsed += _SPEED * dt
            if self.elapsed >= self.perim:
                self.elapsed = self.perim
                self.phase   = self._FINISH
                self.phase_t = now

        elif self.phase == self._FINISH:
            if now - self.phase_t >= _FINISH_S:
                self.win.hide()
                sys.exit(0)

        self.win.queue_draw()
        return True

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _sample_arc(self):
        arc = max(0.0, self.elapsed)
        n   = max(2, int(arc / 5))
        return [_xy(self.start_d + arc * i / n, self.perim, self.sw, self.sh)
                for i in range(n + 1)]

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _on_draw(self, widget, cr: cairo.Context) -> bool:
        # Fully transparent base
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        pts = self._sample_arc()
        if len(pts) < 2:
            return False

        # Brightness multiplier (breathing flash + fade-out on finish)
        if self.phase == self._FINISH:
            age     = time.monotonic() - self.phase_t
            t       = age / _FINISH_S
            breathe = 0.5 + 0.5 * math.cos(age * math.pi * 1.8)
            fade    = max(0.0, 1.0 - t ** 0.6)
            boost   = (1.0 + breathe * 0.4) * fade
        else:
            boost = 1.0

        # Draw glow layers (outer → inner)
        for lw, la in _LAYERS:
            cr.set_source_rgba(_R, _G, _B, la * boost)
            cr.set_line_width(lw)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            x0, y0 = pts[0]
            cr.move_to(x0, y0)
            for x, y in pts[1:]:
                cr.line_to(x, y)
            cr.stroke()

        # Bright white dot at head
        hx, hy = pts[-1]
        cr.set_source_rgba(1.0, 1.0, 1.0, boost)
        cr.arc(hx, hy, 5, 0, 2 * math.pi)
        cr.fill()

        return False


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    GlowSnake()
    Gtk.main()
