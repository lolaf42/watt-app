"""Floating pill HUD overlay."""

import base64
import io
import math
import os
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from battery import BatteryState

# ── Fonts ──────────────────────────────────────────────────────────────────────

_FONTS_BOLD = [
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]
_FONTS_REG = [
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

def _find_font(candidates, size):
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

# ── Colors ─────────────────────────────────────────────────────────────────────

def charge_color(percent: int) -> tuple[int, int, int]:
    if percent >= 60: return (0, 200, 60)
    if percent >= 25: return (255, 140, 0)
    if percent >= 10: return (220, 70, 0)
    return (200, 30, 30)

def _status_color(state: BatteryState) -> tuple[int, int, int]:
    if state.is_charging or state.is_full: return (0, 204, 0)
    return charge_color(state.percent)

# ── Layout ─────────────────────────────────────────────────────────────────────

_CHROMA     = (1, 1, 1)
_CHROMA_HEX = "#010101"
_WIN_ALPHA  = 0.92

W, H, R  = 340, 76, 38          # pill dimensions
PAD      = 12                    # padding around pill for glow
BORDER   = 2
ICON_CX  = 24
PAD_LEFT = 52
CW, CH   = W + 2*PAD, H + 2*PAD # total canvas / window size

# ── Perimeter math ─────────────────────────────────────────────────────────────

def _pill_perim(gw, gh, gr):
    return 2*(gw - 2*gr) + 2*math.pi*gr

def _pill_xy(dist, ox, oy, gw, gh, gr):
    perim = _pill_perim(gw, gh, gr)
    d = dist % perim
    aq = math.pi * gr / 2
    st = gw - 2*gr
    if d < aq:
        t = math.pi*(1 - d/aq*0.5)
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

def _border_pts(target, n=600):
    perim = _pill_perim(W, H, R)
    pts = []
    for i in range(n+1):
        dist = perim*i/n
        if dist > target: break
        pts.append(_pill_xy(dist, PAD, PAD, W, H, R))
    return pts

# ── Drawing helpers ────────────────────────────────────────────────────────────

def _draw_charge_border(d, percent):
    if percent <= 0: return
    color = charge_color(percent)
    perim = _pill_perim(W, H, R)
    pts   = _border_pts(perim * min(percent, 100) / 100)
    if len(pts) >= 2:
        d.line(pts, fill=(*color, 170), width=3)

def _draw_snake(d, snake_progress, percent, lw_px):
    if snake_progress <= 0: return
    color  = charge_color(percent)
    bright = tuple(min(c+80, 255) for c in color)
    perim  = _pill_perim(W, H, R)
    pts    = _border_pts(perim * min(snake_progress, 1.0))
    if len(pts) < 2: return
    lw = max(2, lw_px)
    d.line(pts, fill=(*color, 30),  width=lw*5)
    d.line(pts, fill=(*color, 90),  width=lw*2)
    d.line(pts, fill=(*color, 230), width=lw)
    hx, hy = pts[-1]
    r = max(3, lw+1)
    d.ellipse([hx-r, hy-r, hx+r, hy+r],   fill=(*bright, 255))
    d.ellipse([hx-r//2, hy-r//2, hx+r//2, hy+r//2], fill=(255,255,255,255))

def _draw_battery_icon(d, cx, cy, percent, is_charging, color):
    bw, bh = 26, 13
    x1, y1 = cx-bw//2, cy-bh//2
    x2, y2 = x1+bw, y1+bh
    c = (*color, 255)
    d.rectangle([x2, cy-3, x2+3, cy+3], fill=c)
    d.rectangle([x1, y1, x2, y2], outline=c, width=2)
    fw = int((bw-4)*percent/100)
    if fw > 0:
        d.rectangle([x1+2, y1+2, x1+2+fw, y2-2], fill=c)
    if is_charging:
        bx = cx
        bolt = [(bx+1,y1+1),(bx-4,cy),(bx,cy),(bx-1,y2-1),(bx+5,cy),(bx+1,cy)]
        d.polygon(bolt, fill=(255,240,60,255))

def make_pill_image(state: BatteryState,
                    snake_progress: float = 0.0,
                    lw_px: int = 4) -> Image.Image:
    color    = _status_color(state)
    gc_col   = charge_color(state.percent)

    # ── Layer 1: soft outer glow on transparent canvas ────────────────────────
    pill = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    glow = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    gd.rounded_rectangle([PAD, PAD, CW-PAD-1, CH-PAD-1],
                          radius=R, fill=(*gc_col, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(PAD-2))
    pill = Image.alpha_composite(pill, glow)

    # ── Layer 2: pill body ────────────────────────────────────────────────────
    d = ImageDraw.Draw(pill)
    d.rounded_rectangle([PAD, PAD, CW-PAD-1, CH-PAD-1],
                         radius=R, fill=(13, 13, 13, 252))
    d.rounded_rectangle([PAD, PAD, CW-PAD-1, CH-PAD-1],
                         radius=R, outline=(55, 55, 55, 140), width=BORDER)

    # ── Layer 3: charge border + snake ────────────────────────────────────────
    _draw_charge_border(d, state.percent)
    if snake_progress > 0:
        _draw_snake(d, snake_progress, state.percent, lw_px)

    # ── Layer 4: icon + text ──────────────────────────────────────────────────
    _draw_battery_icon(d, PAD+ICON_CX, PAD+H//2,
                       state.percent, state.is_charging, color)
    ft = _find_font(_FONTS_BOLD, 17)
    fs = _find_font(_FONTS_REG,  12)
    d.text((PAD+PAD_LEFT, PAD+H//2-16), state.HUD_title,
           font=ft, fill=(238, 238, 238, 255))
    d.text((PAD+PAD_LEFT, PAD+H//2+4),  state.HUD_subtitle,
           font=fs, fill=(145, 145, 145, 255))

    # ── Composite onto chroma-key background (transparent corners) ────────────
    final = Image.new("RGB", (CW, CH), _CHROMA)
    final.paste(pill.convert("RGB"), mask=pill.split()[3])
    return final

# ── HUD window ─────────────────────────────────────────────────────────────────

class HudOverlay:
    DISMISS_MS = 4000
    FADE_STEPS = 20
    FADE_MS    = 25

    def __init__(self, root: tk.Tk, config=None):
        self._root   = root
        self._config = config
        self._win:        Optional[tk.Toplevel]   = None
        self._label:      Optional[tk.Label]      = None
        self._photo:      Optional[tk.PhotoImage] = None
        self._dismiss_id: Optional[str]           = None
        self._preview_speed: Optional[int] = None
        self._preview_lw:    Optional[int] = None

    # ── Public ────────────────────────────────────────────────────────────────

    def show(self, state: BatteryState) -> None:
        self._preview_speed = None
        self._preview_lw    = None
        self._root.after(0, lambda: self._show(state))

    def preview_show(self, state: BatteryState,
                     snake_speed=None, line_width_pct=None) -> None:
        self._preview_speed = snake_speed
        self._preview_lw    = line_width_pct
        self._root.after(0, lambda: self._show(state))

    def hide(self) -> None:
        self._root.after(0, self._destroy)

    # ── Config ────────────────────────────────────────────────────────────────

    def _hud_cfg(self) -> dict:
        return self._config.data.get("hud", {}) if self._config else {}

    def _glow_cfg(self) -> dict:
        return self._config.data.get("glow", {}) if self._config else {}

    def _calc_pos(self) -> tuple[int, int]:
        cfg    = self._hud_cfg()
        pos_v  = cfg.get("position_v", 5)
        pos_h  = cfg.get("position_h", 50)
        sw     = self._root.winfo_screenwidth()
        sh     = self._root.winfo_screenheight()
        mt, mb, ml, mr = 40, 60, 20, 20
        x = ml + int((sw - CW - ml - mr) * pos_h / 100)
        y = mt + int((sh - CH - mt - mb) * pos_v / 100)
        return x, y

    def _lw_px(self) -> int:
        gc  = self._glow_cfg()
        pct = self._preview_lw if self._preview_lw is not None \
              else gc.get("line_width_pct", 120)
        return max(1, int(pct / 30))

    def _anim_speed(self) -> float:
        return self._hud_cfg().get("anim_speed", 1.0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _show(self, state: BatteryState) -> None:
        self._destroy()
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=_CHROMA_HEX)
        try:
            win.wm_attributes("-transparentcolor", _CHROMA_HEX)
        except Exception:
            pass
        win.attributes("-alpha", _WIN_ALPHA)
        self._win   = win
        self._label = None
        self._redraw(state)
        x, y = self._calc_pos()
        win.geometry(f"{CW}x{CH}+{x}+{y}")

        anim  = self._hud_cfg().get("animation", "bounce")
        spd   = max(0.25, self._anim_speed())
        delay = 0
        if anim == "fade":
            win.attributes("-alpha", 0.0)
            self._anim_fade_in(steps=max(5, int(15/spd)))
        elif anim == "bounce":
            self._anim_bounce(x, y, steps=max(8, int(22/spd)))
            delay = int(380/spd)
        self._root.after(delay, lambda: self._anim_snake(state))
        self._schedule_dismiss()

    def _redraw(self, state: BatteryState, snake_progress: float = 0.0) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        img = make_pill_image(state, snake_progress=snake_progress,
                              lw_px=self._lw_px())
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        if self._label and self._label.winfo_exists():
            self._label.configure(image=self._photo)
        else:
            self._label = tk.Label(self._win, image=self._photo,
                                   bg=_CHROMA_HEX, borderwidth=0)
            self._label.pack()

    # ── Animations ────────────────────────────────────────────────────────────

    def _anim_fade_in(self, step=0, steps=15):
        if not self._win or not self._win.winfo_exists(): return
        self._win.attributes("-alpha", _WIN_ALPHA*(step+1)/steps)
        if step < steps-1:
            self._root.after(16, lambda: self._anim_fade_in(step+1, steps))

    def _anim_bounce(self, tx, ty, steps=22):
        pos_v   = self._hud_cfg().get("position_v", 5)
        sh      = self._root.winfo_screenheight()
        start_y = sh+CH if pos_v > 50 else -CH

        def _ease(t):
            c1, c3 = 1.70158, 2.70158
            return 1 + c3*(t-1)**3 + c1*(t-1)**2

        def _step(i):
            if not self._win or not self._win.winfo_exists(): return
            y = int(start_y + (ty-start_y)*_ease((i+1)/steps))
            self._win.geometry(f"+{tx}+{y}")
            if i < steps-1:
                self._root.after(16, lambda: _step(i+1))
        _step(0)

    def _anim_snake(self, state, step=0, steps=0):
        if steps == 0:
            gc    = self._glow_cfg()
            spd   = max(0.25, self._anim_speed())
            speed = self._preview_speed if self._preview_speed is not None \
                    else gc.get("snake_speed", 600)
            perim = _pill_perim(W, H, R)
            base  = max(20, min(120, int(perim/speed*1000/16)))
            steps = max(8, int(base/spd))
        if not self._win or not self._win.winfo_exists(): return
        t = (step+1)/steps
        self._redraw(state, snake_progress=1-(1-t)**2)
        if step < steps-1:
            self._root.after(16, lambda: self._anim_snake(state, step+1, steps))

    # ── Dismiss ───────────────────────────────────────────────────────────────

    def _schedule_dismiss(self):
        if self._dismiss_id:
            self._root.after_cancel(self._dismiss_id)
        self._dismiss_id = self._root.after(self.DISMISS_MS, self._start_fade)

    def _start_fade(self):
        self._fade_step(self.FADE_STEPS)

    def _fade_step(self, n):
        if not self._win or not self._win.winfo_exists(): return
        if n <= 0:
            self._destroy(); return
        try:
            self._win.attributes("-alpha", _WIN_ALPHA*n/self.FADE_STEPS)
        except Exception:
            pass
        self._root.after(self.FADE_MS, lambda: self._fade_step(n-1))

    def _destroy(self):
        if self._dismiss_id:
            self._root.after_cancel(self._dismiss_id)
            self._dismiss_id = None
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = self._label = None

# ── BatteryState display helpers ───────────────────────────────────────────────

def hud_title(state):
    if not state.has_battery: return "No Battery"
    if state.is_full:         return "Fully Charged"
    if state.is_charging:     return f"Charging — {state.percent}%"
    return f"{state.percent}% Remaining"

def hud_subtitle(state):
    if not state.has_battery:                         return "No battery detected"
    if state.is_full:                                 return "Battery is full"
    if not state.is_charging and state.percent <= 5:  return "Connect charger immediately"
    if state.seconds_remaining is None:               return "Calculating..."
    label = "until full" if state.is_charging else "until empty"
    return f"{state.time_remaining_text} {label}"

BatteryState.HUD_title    = property(hud_title)
BatteryState.HUD_subtitle = property(hud_subtitle)
