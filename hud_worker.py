#!/usr/bin/env python3
"""HUD pill — GTK/Cairo subprocess with real RGBA transparency (Wayland-safe)."""

import json, math, sys
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gtk, Gdk, GLib
import cairo

# ── Layout ─────────────────────────────────────────────────────────────────────
W, H, R = 340, 72, 36      # pill width, height, corner radius
PAD     = 2                 # minimal padding for anti-aliasing
CW, CH  = W + 2*PAD, H + 2*PAD

DISMISS_MS = 5000
FADE_MS    = 500


# ── Perimeter math ─────────────────────────────────────────────────────────────

def _perim():
    return 2 * (W - 2*R) + 2 * math.pi * R


def _pill_xy(dist):
    gw, gh, gr = W, H, R
    ox, oy = PAD, PAD
    d = dist % _perim()
    aq = math.pi * gr / 2
    st = gw - 2 * gr
    if d < aq:
        t = math.pi * (1 - d / aq * 0.5)
        return ox+gr+gr*math.cos(t), oy+gr-gr*math.sin(t)
    d -= aq
    if d < st: return ox+gr+d, float(oy)
    d -= st
    if d < aq:
        t = math.pi/2*(1-d/aq)
        return ox+gw-gr+gr*math.cos(t), oy+gr-gr*math.sin(t)
    d -= aq
    if d < aq:
        t = -math.pi/2*d/aq
        return ox+gw-gr+gr*math.cos(t), oy+gr-gr*math.sin(t)
    d -= aq
    if d < st: return ox+gw-gr-d, float(oy+gh)
    d -= st
    t = -math.pi/2*(1+min(d/aq, 1.0))
    return ox+gr+gr*math.cos(t), oy+gr-gr*math.sin(t)


def _pill_pts(fraction, n=400):
    target = _perim() * max(0.0, min(1.0, fraction))
    return [_pill_xy(target * i / n) for i in range(n + 1)]


def _rounded_rect(cr, x, y, w, h, r):
    cr.arc(x+w-r, y+r,   r, -math.pi/2, 0)
    cr.arc(x+w-r, y+h-r, r, 0,           math.pi/2)
    cr.arc(x+r,   y+h-r, r, math.pi/2,   math.pi)
    cr.arc(x+r,   y+r,   r, math.pi,     3*math.pi/2)
    cr.close_path()


# ── Color helper ───────────────────────────────────────────────────────────────

def _charge_color(pct):
    if pct >= 60: return (0.13, 0.78, 0.35)    # green
    if pct >= 25: return (1.00, 0.62, 0.07)    # orange
    if pct >= 10: return (0.95, 0.40, 0.05)    # deep orange
    return            (0.88, 0.18, 0.18)        # red


# ── Main window ────────────────────────────────────────────────────────────────

# Alert-mode ring colours (RGB 0–1)
_ALERT_COL = {
    "critical": (0.80, 0.13, 0.13),
    "warning":  (0.85, 0.50, 0.00),
    "high":     (0.15, 0.75, 0.25),
    "info":     (0.18, 0.53, 0.88),
}


class HudWindow(Gtk.Window):
    def __init__(self, cfg):
        super().__init__()
        self._cfg    = cfg
        self._alpha  = 0.0
        self._snake  = 0.0
        self._pulse  = 0.0   # 0..1, used in alert mode

        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_app_paintable(True)
        self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        self.set_accept_focus(False)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        self.set_default_size(CW, CH)
        self.move(cfg["x"], cfg["y"])
        self.connect("draw", self._draw)
        self.connect("destroy", Gtk.main_quit)
        if cfg.get("alert"):
            self.connect("map-event", self._on_mapped)
        self.show_all()
        GLib.idle_add(self._start_enter)

    def _on_mapped(self, _widget, _event):
        """Position alert HUD using configured h/v percentages within work area."""
        ph = self._cfg.get("alert_pos_h", 50) / 100
        pv = self._cfg.get("alert_pos_v", 50) / 100
        try:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor() or display.get_monitor(0)
            wa      = monitor.get_workarea()
            margin  = 12
            x = wa.x + margin + int((wa.width  - CW - 2 * margin) * ph)
            y = wa.y + margin + int((wa.height - CH - 2 * margin) * pv)
        except Exception:
            screen  = self.get_screen()
            margin  = 12
            x = margin + int((screen.get_width()  - CW - 2 * margin) * ph)
            y = margin + int((screen.get_height() - CH - 2 * margin) * pv)
        self.move(x, y)
        return False

    # ── Draw ───────────────────────────────────────────────────────────────────

    def _draw(self, _w, cr):
        c   = self._cfg
        a   = self._alpha
        pct = c["percent"]
        col = _charge_color(pct)

        # Fully transparent canvas
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # ── Pill background — neutral dark grey like reference ─────────────
        lv = c["bg"] / 100.0
        br = 0.14 + lv * 0.40   # slight cool-grey tint matches reference
        bg_r, bg_g, bg_b = br, br + 0.02, br + 0.05
        cr.set_source_rgba(bg_r, bg_g, bg_b, c["win_alpha"] * a)
        _rounded_rect(cr, PAD, PAD, W, H, R)
        cr.fill()

        # ── Subtle inner border ────────────────────────────────────────────
        cr.set_source_rgba(bg_r + 0.25, bg_g + 0.25, bg_b + 0.25, 0.30 * a)
        _rounded_rect(cr, PAD, PAD, W, H, R)
        cr.set_line_width(1.0)
        cr.stroke()

        # ── Charge arc (static, proportional to battery %) ────────────────
        if pct > 0:
            pts = _pill_pts(pct / 100)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Background-color halo — separates arc from pill border
            cr.set_line_width(11.5)
            cr.set_source_rgba(bg_r, bg_g, bg_b, a)
            cr.move_to(*pts[0])
            for p in pts[1:]: cr.line_to(*p)
            cr.stroke()
            # Colored arc on top
            cr.set_line_width(4.0)
            cr.set_source_rgba(*col, 0.92 * a)
            cr.move_to(*pts[0])
            for p in pts[1:]: cr.line_to(*p)
            cr.stroke()

        # ── Alert ring (replaces snake in alert mode) ─────────────────────
        if self._cfg.get("alert"):
            level = self._cfg.get("alert_level", "warning")
            rc, gc, bc = _ALERT_COL.get(level, _ALERT_COL["warning"])
            p = self._pulse   # 0..1 sine wave

            # Layer 1 — wide soft outer halo
            cr.set_source_rgba(rc, gc, bc, 0.30 * a * p)
            _rounded_rect(cr, PAD - 10, PAD - 10, W + 20, H + 20, R + 10)
            cr.set_line_width(14.0)
            cr.stroke()

            # Layer 2 — medium halo
            cr.set_source_rgba(rc, gc, bc, 0.45 * a * p)
            _rounded_rect(cr, PAD - 5, PAD - 5, W + 10, H + 10, R + 5)
            cr.set_line_width(8.0)
            cr.stroke()

            # Layer 3 — sharp main border, width pulses between 4 and 9
            lw = 4.0 + 5.0 * p
            cr.set_source_rgba(rc, gc, bc, (0.70 + 0.30 * p) * a)
            _rounded_rect(cr, PAD, PAD, W, H, R)
            cr.set_line_width(lw)
            cr.stroke()

            # Inner tint fill
            cr.set_source_rgba(rc, gc, bc, 0.14 * a * p)
            _rounded_rect(cr, PAD, PAD, W, H, R)
            cr.fill()

        # ── Snake (charging animation, normal mode only) ───────────────────
        if self._snake > 0 and not self._cfg.get("alert"):
            lw  = max(1, c["lw_pct"] // 30)
            pts = _pill_pts(self._snake)
            if len(pts) >= 2:
                bright = tuple(min(1.0, v + 0.25) for v in col)
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                for width, src_a in [(lw*5, 0.10), (lw*2, 0.35), (lw, 0.92)]:
                    cr.set_line_width(width)
                    cr.set_source_rgba(*col, src_a * a)
                    cr.move_to(*pts[0])
                    for p in pts[1:]: cr.line_to(*p)
                    cr.stroke()
                hx, hy = pts[-1]
                cr.set_source_rgba(*bright, a)
                cr.arc(hx, hy, lw + 1, 0, 2*math.pi)
                cr.fill()
                cr.set_source_rgba(1, 1, 1, a)
                cr.arc(hx, hy, max(1, lw//2), 0, 2*math.pi)
                cr.fill()

        # ── Battery icon ───────────────────────────────────────────────────
        cx, cy = PAD + 28, PAD + H // 2
        bw, bh = 28, 14
        x1, y1 = cx - bw//2, cy - bh//2
        cr.set_source_rgba(*col, a)
        cr.rectangle(x1+bw, cy-3, 3, 6)
        cr.fill()
        _rounded_rect(cr, x1, y1, bw, bh, 3)
        cr.set_line_width(1.8)
        cr.stroke()
        fw = int((bw - 5) * pct / 100)
        if fw > 0:
            _rounded_rect(cr, x1+2, y1+2, fw, bh-4, 2)
            cr.fill()
        if c["is_charging"]:
            bx = cx
            cr.set_source_rgba(1, 0.94, 0.24, a)
            cr.move_to(bx+1, y1+1)
            cr.line_to(bx-4, cy)
            cr.line_to(bx,   cy)
            cr.line_to(bx-1, y1+bh-1)
            cr.line_to(bx+5, cy)
            cr.line_to(bx+1, cy)
            cr.close_path()
            cr.fill()

        # ── Text ───────────────────────────────────────────────────────────
        tx = PAD + 66

        title_text    = c.get("alert_title",    c["title"])
        subtitle_text = c.get("alert_subtitle", c["subtitle"])

        cr.set_source_rgba(0.97, 0.97, 0.97, a)
        cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(18)
        cr.move_to(tx, PAD + H//2 - 1)
        cr.show_text(title_text)

        cr.set_source_rgba(0.62, 0.66, 0.72, a)
        cr.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(12)
        cr.move_to(tx, PAD + H//2 + 17)
        cr.show_text(subtitle_text)

    # ── Animations ─────────────────────────────────────────────────────────────

    def _start_enter(self):
        anim = self._cfg.get("anim", "bounce")
        spd  = max(0.25, self._cfg.get("anim_speed", 1.0))
        wa   = self._cfg.get("win_alpha", 0.88)
        steps = {"fade":   max(6,  int(18/spd)),
                 "slide":  max(8,  int(22/spd)),
                 "bounce": max(10, int(30/spd))}.get(anim, 0)
        if anim == "none":
            self._alpha = wa; self.queue_draw(); self._after_enter()
        elif anim == "fade":   self._fade_in(0, steps, wa)
        elif anim == "slide":  self._slide_in(0, steps, wa)
        else:                  self._bounce_in(0, steps, wa)
        return False

    def _after_enter(self):
        if self._cfg.get("alert"):
            self._pulse_step(0)
            GLib.timeout_add(DISMISS_MS, self._start_dismiss)
        else:
            spd   = max(0.25, self._cfg.get("anim_speed", 1.0))
            speed = self._cfg.get("snake_speed", 600)
            perim = _perim()
            n     = max(20, int(perim / speed * 62.5 / spd))
            self._snake_step(0, n)
            GLib.timeout_add(DISMISS_MS, self._start_dismiss)

    def _pulse_step(self, i):
        # Faster (0.15 step) + power curve for sharper peaks
        t = (math.sin(i * 0.15) + 1) / 2
        self._pulse = t * t        # quadratic → dim valleys, bright peaks
        self.queue_draw()
        GLib.timeout_add(22, lambda: self._pulse_step(i + 1) or False)

    def _fade_in(self, i, n, wa):
        # Pure alpha fade — no movement
        p = (i+1)/n
        self._alpha = wa * p*p*(3-2*p)   # smooth-step
        self.queue_draw()
        if i < n-1: GLib.timeout_add(16, lambda: self._fade_in(i+1,n,wa) or False)
        else: self._alpha=wa; self._after_enter()

    def _slide_in(self, i, n, wa):
        # Ease-out-quart slide + fade — smooth deceleration, no overshoot
        p   = (i+1)/n
        off = 120 if self._cfg.get("pos_v",5) > 50 else -120
        ease = 1-(1-p)**4
        self.move(self._cfg["x"],
                  self._cfg["y"] + int(off*(1-ease)))
        self._alpha = min(wa, wa*p*2.0)
        self.queue_draw()
        if i < n-1: GLib.timeout_add(16, lambda: self._slide_in(i+1,n,wa) or False)
        else: self.move(self._cfg["x"],self._cfg["y"]); self._alpha=wa; self._after_enter()

    def _bounce_in(self, i, n, wa):
        # Elastic spring — overshoots target then settles
        p  = (i+1)/n
        c4 = math.pi*0.90
        sp = pow(2,-10*p)*math.sin((p*10-0.75)*c4)+1 if p<1 else 1.0
        off = 140 if self._cfg.get("pos_v",5) > 50 else -140
        self.move(self._cfg["x"], self._cfg["y"] + int(off*(1-sp)))
        self._alpha = min(wa, wa*p*3.5)
        self.queue_draw()
        if i < n-1: GLib.timeout_add(16, lambda: self._bounce_in(i+1,n,wa) or False)
        else: self.move(self._cfg["x"],self._cfg["y"]); self._alpha=wa; self._after_enter()

    def _snake_step(self, i, n):
        t = (i+1)/n
        self._snake = 1-(1-t)**2
        self.queue_draw()
        if i < n-1: GLib.timeout_add(16, lambda: self._snake_step(i+1,n) or False)

    def _start_dismiss(self):
        n = max(8, FADE_MS//25)
        wa = self._cfg.get("win_alpha", 0.88)
        self._dismiss_step(0, n, wa)
        return False

    def _dismiss_step(self, i, n, wa):
        t = (i+1)/n
        self._alpha = wa*(1-t*t*(3-2*t))
        self.queue_draw()
        if i < n-1: GLib.timeout_add(25, lambda: self._dismiss_step(i+1,n,wa) or False)
        else: self.destroy()


if __name__ == "__main__":
    cfg = json.loads(sys.argv[1])
    HudWindow(cfg)
    Gtk.main()
