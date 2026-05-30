#!/usr/bin/env python3
"""GTK3/Cairo combined glow effect.

One fullscreen RGBA window draws two things simultaneously:
  1. Screen-edge glow  — wide breathing gradient on all 4 sides (like reference image)
  2. Pill snake        — growing line around the HUD battery pill

Sequence:
  GROWING : screen border at base brightness + pill snake grows
  FINISH  : everything breathes once then fades out → process exits

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

# ── Screen-border glow ────────────────────────────────────────────────────────
_BORDER_W = 70          # glow width (px) inward from each screen edge

# ── Pill snake (must match hud.py dimensions) ─────────────────────────────────
_PILL_W = 340
_PILL_H = 76
_PILL_R = 38
_PILL_Y = 60
_M      = 14            # margin outside pill for the snake glow
_GW     = _PILL_W + 2 * _M   # 368
_GH     = _PILL_H + 2 * _M   # 104
_GR     = _PILL_R + _M        # 52

# ── Timing ────────────────────────────────────────────────────────────────────
_SPEED    = 600         # px/s along pill perimeter
_FINISH_S = 1.5         # breathing + fade after snake completes
_FPS      = 60

# ── Snake glow layers: (line_width, alpha) ────────────────────────────────────
_SNAKE_LAYERS = [(22, 0.08), (10, 0.40), (4, 1.00)]


# ── Pill perimeter math ───────────────────────────────────────────────────────

def _pill_perim(gw, gh, gr):
    return 2 * (gw - 2 * gr) + 2 * math.pi * gr


def _pill_xy(d, gx, gy, gw, gh, gr):
    """Perimeter distance → screen (x,y), clockwise from left-centre going up."""
    perim = _pill_perim(gw, gh, gr)
    d     = d % perim
    aq    = math.pi * gr / 2
    st    = gw - 2 * gr

    if d < aq:                                          # top-left arc
        t = math.pi * (1 - d / aq * 0.5)
        return gx + gr + gr * math.cos(t), gy + gr - gr * math.sin(t)
    d -= aq
    if d < st:                                          # top edge
        return gx + gr + d, gy
    d -= st
    if d < aq:                                          # top-right arc
        t = math.pi / 2 * (1 - d / aq)
        return gx + gw - gr + gr * math.cos(t), gy + gr - gr * math.sin(t)
    d -= aq
    if d < aq:                                          # bottom-right arc
        t = -math.pi / 2 * d / aq
        return gx + gw - gr + gr * math.cos(t), gy + gr - gr * math.sin(t)
    d -= aq
    if d < st:                                          # bottom edge
        return gx + gw - gr - d, gy + gh
    d -= st
    frac = min(d / aq, 1.0)                             # bottom-left arc
    t = -math.pi / 2 * (1 + frac)
    return gx + gr + gr * math.cos(t), gy + gr - gr * math.sin(t)


# ── Main effect window ────────────────────────────────────────────────────────

class GlowEffect:

    _GROWING = "growing"
    _FINISH  = "finish"

    def __init__(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        geo     = monitor.get_geometry()
        self.sw, self.sh = geo.width, geo.height

        # Pill snake window-local origin (relative to fullscreen canvas)
        self.pill_lx = (self.sw - _PILL_W) // 2 - _M
        self.pill_ly = _PILL_Y - _M

        self.perim   = _pill_perim(_GW, _GH, _GR)
        self.elapsed  = 0.0
        self.last_t   = time.monotonic()
        self.phase    = self._GROWING
        self.phase_t  = 0.0

        # ── Fullscreen RGBA window ────────────────────────────────────────────
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
        win.input_shape_combine_region(cairo.Region())   # click-through

        self.win = win
        GLib.timeout_add(1000 // _FPS, self._tick)

    # ── Loop ─────────────────────────────────────────────────────────────────

    def _tick(self):
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

    # ── Drawing ──────────────────────────────────────────────────────────────

    def _on_draw(self, widget, cr):
        W, H = self.sw, self.sh

        # Fully transparent base
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Brightness/fade multiplier
        if self.phase == self._FINISH:
            age     = time.monotonic() - self.phase_t
            t       = age / _FINISH_S
            breathe = 0.5 + 0.5 * math.cos(age * math.pi * 1.8)
            fade    = max(0.0, 1.0 - t ** 0.55)
            boost   = (1.0 + breathe * 0.45) * fade
        else:
            boost = 1.0

        # ── 1. Screen-edge border glow ───────────────────────────────────────
        bw = _BORDER_W
        r, g, b = _R, _G, _B

        def _edge(x, y, w, h, gx0, gy0, gx1, gy1):
            pat = cairo.LinearGradient(gx0, gy0, gx1, gy1)
            pat.add_color_stop_rgba(0.00, r, g, b, boost * 1.00)
            pat.add_color_stop_rgba(0.15, r, g, b, boost * 0.88)
            pat.add_color_stop_rgba(0.38, r, g, b, boost * 0.50)
            pat.add_color_stop_rgba(0.62, r, g, b, boost * 0.15)
            pat.add_color_stop_rgba(0.82, r, g, b, boost * 0.04)
            pat.add_color_stop_rgba(1.00, r, g, b, 0.00)
            cr.set_source(pat)
            cr.rectangle(x, y, w, h)
            cr.fill()

        _edge(0,      0,      W,  bw, 0, 0,      0, bw)      # top
        _edge(0,      H - bw, W,  bw, 0, H,      0, H - bw)  # bottom
        _edge(0,      0,      bw, H,  0, 0,      bw, 0)       # left
        _edge(W - bw, 0,      bw, H,  W, 0,      W - bw, 0)   # right

        # ── 2. Pill snake ────────────────────────────────────────────────────
        arc   = max(0.0, self.elapsed)
        n     = max(2, int(arc / 4))
        lx    = self.pill_lx
        ly    = self.pill_ly
        pts   = [_pill_xy(arc * i / n, lx, ly, _GW, _GH, _GR) for i in range(n + 1)]

        if len(pts) >= 2:
            for lw, la in _SNAKE_LAYERS:
                cr.set_source_rgba(r, g, b, la * boost)
                cr.set_line_width(lw)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.set_line_join(cairo.LINE_JOIN_ROUND)
                x0, y0 = pts[0]
                cr.move_to(x0, y0)
                for px, py in pts[1:]:
                    cr.line_to(px, py)
                cr.stroke()

            # White dot at snake head
            hx, hy = pts[-1]
            cr.set_source_rgba(1, 1, 1, boost)
            cr.arc(hx, hy, 4, 0, 2 * math.pi)
            cr.fill()

        return False


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    GlowEffect()
    Gtk.main()
