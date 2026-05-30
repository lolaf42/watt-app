#!/usr/bin/env python3
"""Screen border glow — fullscreen transparent RGBA window, border only.

Pill snake animation is now drawn inside the HUD window itself.

Usage: python3 glow_worker.py <r> <g> <b> <border_intensity_%> <border_duration_s>
"""

import os
os.environ.setdefault("GDK_BACKEND", "x11")

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

import cairo
import sys
import time

_R, _G, _B    = int(sys.argv[1])/255, int(sys.argv[2])/255, int(sys.argv[3])/255
_BORDER_ALPHA = int(sys.argv[4])/100 if len(sys.argv) > 4 else 1.0
_DURATION     = float(sys.argv[5]) if len(sys.argv) > 5 else 3.0
_FADE_S       = 1.0
_BORDER_W     = 70
_FPS          = 60


class BorderGlow:

    def __init__(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        geo     = monitor.get_geometry()
        self.sw, self.sh = geo.width, geo.height
        self.start_t = time.monotonic()

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
        win.connect("draw", self._on_draw)
        win.show_all()
        win.move(geo.x, geo.y)
        win.resize(self.sw, self.sh)
        win.input_shape_combine_region(cairo.Region())

        self.win = win
        GLib.timeout_add(1000 // _FPS, self._tick)

    def _tick(self):
        age = time.monotonic() - self.start_t
        if age >= _DURATION + _FADE_S:
            self.win.hide()
            sys.exit(0)
        self.win.queue_draw()
        return True

    def _on_draw(self, widget, cr):
        W, H = self.sw, self.sh
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        age  = time.monotonic() - self.start_t
        fade = max(0.0, 1.0 - (age - _DURATION) / _FADE_S) if age > _DURATION else 1.0
        bi   = _BORDER_ALPHA * fade
        r, g, b = _R, _G, _B
        bw = _BORDER_W

        def _edge(x, y, w, h, gx0, gy0, gx1, gy1):
            pat = cairo.LinearGradient(gx0, gy0, gx1, gy1)
            pat.add_color_stop_rgba(0.00, r, g, b, bi * 1.00)
            pat.add_color_stop_rgba(0.15, r, g, b, bi * 0.88)
            pat.add_color_stop_rgba(0.38, r, g, b, bi * 0.50)
            pat.add_color_stop_rgba(0.62, r, g, b, bi * 0.15)
            pat.add_color_stop_rgba(0.82, r, g, b, bi * 0.04)
            pat.add_color_stop_rgba(1.00, r, g, b, 0.00)
            cr.set_source(pat)
            cr.rectangle(x, y, w, h)
            cr.fill()

        _edge(0,      0,      W,  bw, 0, 0,   0, bw)
        _edge(0,      H - bw, W,  bw, 0, H,   0, H - bw)
        _edge(0,      0,      bw, H,  0, 0,   bw, 0)
        _edge(W - bw, 0,      bw, H,  W, 0,   W - bw, 0)
        return False


if __name__ == "__main__":
    BorderGlow()
    Gtk.main()
