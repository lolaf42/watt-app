#!/usr/bin/env python3
"""GTK3/Cairo growing-snake glow around the HUD battery pill.

A bright line starts at left-center of the pill and grows clockwise:
  left → up → top → right → down → bottom → back to left

On completion: one breath + fade out, then exits.

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

# ── HUD pill geometry (must match hud.py) ─────────────────────────────────────
_PILL_W = 340
_PILL_H = 76
_PILL_R = 38          # corner radius
_PILL_Y = 60          # pill top-y on screen

# ── Glow window: expanded pill + margin around it ─────────────────────────────
_M  = 14              # margin outside pill (px)
_GW = _PILL_W + 2*_M  # 368
_GH = _PILL_H + 2*_M  # 104
_GR = _PILL_R + _M    # 52  — keeps GH == 2*GR (pure pill shape)

# ── Timing ────────────────────────────────────────────────────────────────────
_SPEED    = 600    # px / s along the pill perimeter
_FINISH_S = 1.2    # breathing + fade after loop completes
_FPS      = 60

# ── Glow layers: (line_width_px, alpha) ──────────────────────────────────────
_LAYERS = [(22, 0.08), (10, 0.40), (4, 1.00)]


# ── Pill perimeter parameterisation ──────────────────────────────────────────

def _pill_perim(gw, gh, gr) -> float:
    """Total perimeter of the expanded pill (rounded rect with gh = 2*gr)."""
    return 2 * (gw - 2*gr) + 2 * math.pi * gr


def _pill_xy(d: float, gx: float, gy: float,
             gw: float, gh: float, gr: float) -> tuple:
    """
    Convert perimeter distance d (clockwise from left-center going UP)
    to screen (x, y) on the pill outline.

    Segments (clockwise, starting at left-centre = (gx, gy+gr)):
      1. Top-left quarter-arc  θ: π  → π/2   length = π*gr/2
      2. Top straight          left → right    length = gw - 2*gr
      3. Top-right quarter-arc θ: π/2 → 0     length = π*gr/2
      4. Bottom-right arc      θ: 0  → -π/2   length = π*gr/2
      5. Bottom straight       right → left    length = gw - 2*gr
      6. Bottom-left arc       θ: -π/2 → -π   length = π*gr/2

    Note: y-on-screen = cy - gr*sin(θ)  (y-down coordinate system)
    """
    perim  = _pill_perim(gw, gh, gr)
    d      = d % perim
    aq     = math.pi * gr / 2   # quarter-arc length
    st     = gw - 2 * gr         # straight segment length

    # ── Segment 1: top-left arc ──────────────────────────────────────────────
    if d < aq:
        frac = d / aq
        θ = math.pi * (1 - frac/2)     # π → π/2
        cx, cy = gx + gr, gy + gr
        return cx + gr*math.cos(θ), cy - gr*math.sin(θ)
    d -= aq

    # ── Segment 2: top straight ──────────────────────────────────────────────
    if d < st:
        return gx + gr + d, gy
    d -= st

    # ── Segment 3: top-right arc ─────────────────────────────────────────────
    if d < aq:
        frac = d / aq
        θ = math.pi/2 * (1 - frac)     # π/2 → 0
        cx, cy = gx + gw - gr, gy + gr
        return cx + gr*math.cos(θ), cy - gr*math.sin(θ)
    d -= aq

    # ── Segment 4: bottom-right arc ──────────────────────────────────────────
    if d < aq:
        frac = d / aq
        θ = -math.pi/2 * frac           # 0 → -π/2
        cx, cy = gx + gw - gr, gy + gr
        return cx + gr*math.cos(θ), cy - gr*math.sin(θ)
    d -= aq

    # ── Segment 5: bottom straight ───────────────────────────────────────────
    if d < st:
        return gx + gw - gr - d, gy + gh
    d -= st

    # ── Segment 6: bottom-left arc ───────────────────────────────────────────
    frac = min(d / aq, 1.0)
    θ = -math.pi/2 * (1 + frac)         # -π/2 → -π
    cx, cy = gx + gr, gy + gr
    return cx + gr*math.cos(θ), cy - gr*math.sin(θ)


# ── GTK window ────────────────────────────────────────────────────────────────

class GlowPill:

    _GROWING = "growing"
    _FINISH  = "finish"

    def __init__(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        geo     = monitor.get_geometry()

        sw = geo.width
        pill_x = (sw - _PILL_W) // 2

        # Glow window sits just outside the pill
        self.gx = pill_x - _M
        self.gy = _PILL_Y - _M
        self.gw, self.gh, self.gr = _GW, _GH, _GR

        self.perim   = _pill_perim(_GW, _GH, _GR)
        self.elapsed  = 0.0
        self.last_t   = time.monotonic()
        self.phase    = self._GROWING
        self.phase_t  = 0.0

        # ── Window ───────────────────────────────────────────────────────────
        win = Gtk.Window(type=Gtk.WindowType.POPUP)
        win.set_accept_focus(False)
        win.set_skip_taskbar_hint(True)
        win.set_skip_pager_hint(True)

        screen = win.get_screen()
        rgba   = screen.get_rgba_visual()
        if rgba:
            win.set_visual(rgba)
        win.set_app_paintable(True)

        win.set_default_size(_GW, _GH)
        win.resize(_GW, _GH)
        win.connect("draw", self._on_draw)
        win.show_all()
        win.move(geo.x + self.gx, geo.y + self.gy)
        win.resize(_GW, _GH)
        win.input_shape_combine_region(cairo.Region())

        self.win = win
        GLib.timeout_add(1000 // _FPS, self._tick)

    # ── Loop ─────────────────────────────────────────────────────────────────

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

    # ── Drawing ──────────────────────────────────────────────────────────────

    def _sample_arc(self):
        arc = max(0.0, self.elapsed)
        n   = max(2, int(arc / 4))
        return [_pill_xy(arc * i / n, 0, 0, self.gw, self.gh, self.gr)
                for i in range(n + 1)]

    def _on_draw(self, widget, cr: cairo.Context) -> bool:
        # Fully transparent background
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        pts = self._sample_arc()
        if len(pts) < 2:
            return False

        # Brightness: normal → breathing flash + fade on finish
        if self.phase == self._FINISH:
            age     = time.monotonic() - self.phase_t
            t       = age / _FINISH_S
            breathe = 0.5 + 0.5 * math.cos(age * math.pi * 1.8)
            fade    = max(0.0, 1.0 - t ** 0.6)
            boost   = (1.0 + breathe * 0.4) * fade
        else:
            boost = 1.0

        # Glow layers
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

        # White hot dot at head
        hx, hy = pts[-1]
        cr.set_source_rgba(1, 1, 1, boost)
        cr.arc(hx, hy, 4, 0, 2 * math.pi)
        cr.fill()

        return False


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    GlowPill()
    Gtk.main()
