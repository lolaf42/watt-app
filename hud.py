"""Floating pill HUD overlay — shown on battery state changes."""

import base64
import io
import math
import os
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from battery import BatteryState

# ── Font discovery ─────────────────────────────────────────────────────────────

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


def _find_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ── Color scheme ───────────────────────────────────────────────────────────────

def charge_color(percent: int) -> tuple[int, int, int]:
    if percent >= 60:
        return (0, 200, 60)
    if percent >= 25:
        return (255, 140, 0)
    if percent >= 10:
        return (220, 70, 0)
    return (200, 30, 30)


def _status_color(state: BatteryState) -> tuple[int, int, int]:
    if state.is_charging or state.is_full:
        return (0, 204, 0)
    return charge_color(state.percent)


# ── Pill image renderer ────────────────────────────────────────────────────────

_WIN_BG  = "#080808"   # window background — dark, no chroma key
_WIN_ALPHA = 0.88      # base window transparency

W, H, R  = 340, 76, 38
PAD      = 8           # padding around pill for glow/shadow room
BORDER   = 2
ICON_CX  = 24
PAD_LEFT = 52

# Total canvas size (includes padding)
CW, CH = W + 2 * PAD, H + 2 * PAD


# ── Perimeter math (pill coords inside the padded canvas) ─────────────────────

def _pill_perim(gw: int, gh: int, gr: int) -> float:
    return 2 * (gw - 2 * gr) + 2 * math.pi * gr


def _pill_xy(dist: float, ox: int, oy: int, gw: int, gh: int, gr: int) -> tuple[float, float]:
    """Perimeter distance → (x, y) with offset (ox, oy), clockwise from left-centre."""
    perim = _pill_perim(gw, gh, gr)
    d     = dist % perim
    aq    = math.pi * gr / 2
    st    = gw - 2 * gr

    if d < aq:
        t = math.pi * (1 - d / aq * 0.5)
        return ox + gr + gr * math.cos(t), oy + gr - gr * math.sin(t)
    d -= aq
    if d < st:
        return ox + gr + d, float(oy)
    d -= st
    if d < aq:
        t = math.pi / 2 * (1 - d / aq)
        return ox + gw - gr + gr * math.cos(t), oy + gr - gr * math.sin(t)
    d -= aq
    if d < aq:
        t = -math.pi / 2 * d / aq
        return ox + gw - gr + gr * math.cos(t), oy + gr - gr * math.sin(t)
    d -= aq
    if d < st:
        return ox + gw - gr - d, float(oy + gh)
    d -= st
    frac = min(d / aq, 1.0)
    t = -math.pi / 2 * (1 + frac)
    return ox + gr + gr * math.cos(t), oy + gr - gr * math.sin(t)


def _border_pts(target_dist: float, ox: int = PAD, oy: int = PAD,
                n: int = 600) -> list[tuple[float, float]]:
    perim = _pill_perim(W, H, R)
    pts: list[tuple[float, float]] = []
    for i in range(n + 1):
        dist = perim * i / n
        if dist > target_dist:
            break
        pts.append(_pill_xy(dist, ox, oy, W, H, R))
    return pts


def _draw_charge_border(d: ImageDraw.ImageDraw, percent: int) -> None:
    if percent <= 0:
        return
    color  = charge_color(percent)
    perim  = _pill_perim(W, H, R)
    target = perim * min(percent, 100) / 100
    pts    = _border_pts(target)
    if len(pts) >= 2:
        d.line(pts, fill=(*color, 160), width=3)


def _draw_snake(d: ImageDraw.ImageDraw, snake_progress: float,
                percent: int, line_width: int = 4) -> None:
    if snake_progress <= 0:
        return
    color  = charge_color(percent)
    bright = tuple(min(c + 80, 255) for c in color)
    perim  = _pill_perim(W, H, R)
    target = perim * min(snake_progress, 1.0)
    pts    = _border_pts(target)
    if len(pts) < 2:
        return
    lw = max(2, line_width)
    d.line(pts, fill=(*color, 35),  width=lw * 4)   # wide soft glow
    d.line(pts, fill=(*color, 100), width=lw * 2)   # mid glow
    d.line(pts, fill=(*color, 230), width=lw)        # core
    hx, hy = pts[-1]
    r = max(3, lw)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=(*bright, 255))
    d.ellipse([hx - r//2, hy - r//2, hx + r//2, hy + r//2],
              fill=(255, 255, 255, 255))


def _draw_battery_icon(d, cx, cy, percent, is_charging, color):
    bw, bh = 26, 13
    x1, y1 = cx - bw // 2, cy - bh // 2
    x2, y2 = x1 + bw, y1 + bh
    c = (*color, 255)
    d.rectangle([x2, cy - 3, x2 + 3, cy + 3], fill=c)
    d.rectangle([x1, y1, x2, y2], outline=c, width=2)
    fill_w = int((bw - 4) * percent / 100)
    if fill_w > 0:
        d.rectangle([x1 + 2, y1 + 2, x1 + 2 + fill_w, y2 - 2], fill=c)
    if is_charging:
        bx = cx
        bolt = [(bx + 1, y1 + 1), (bx - 4, cy), (bx, cy),
                (bx - 1, y2 - 1), (bx + 5, cy), (bx + 1, cy)]
        d.polygon(bolt, fill=(255, 240, 60, 255))


def make_pill_image(state: BatteryState, snake_progress: float = 0.0,
                    line_width: int = 4) -> Image.Image:
    color = _status_color(state)

    # Canvas: fully black (matches window background)
    img = Image.new("RGB", (CW, CH), (8, 8, 8))
    d   = ImageDraw.Draw(img)

    # Outer soft glow around pill (blur a slightly larger rounded rect)
    glow_col = charge_color(state.percent)
    glow = Image.new("RGB", (CW, CH), (8, 8, 8))
    gd   = ImageDraw.Draw(glow)
    gd.rounded_rectangle([PAD - 4, PAD - 4, CW - PAD + 3, CH - PAD + 3],
                          radius=R + 4, fill=(*glow_col,))
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    # Blend glow subtly into canvas
    img = Image.blend(img, glow, 0.18)
    d = ImageDraw.Draw(img)

    # Pill background — dark, slightly lighter than pure black
    d.rounded_rectangle([PAD, PAD, CW - PAD - 1, CH - PAD - 1],
                         radius=R, fill=(14, 14, 14))

    # Subtle inner border
    d.rounded_rectangle([PAD, PAD, CW - PAD - 1, CH - PAD - 1],
                         radius=R, outline=(50, 50, 50), width=BORDER)

    # Charge border arc
    _draw_charge_border(d, state.percent)

    # Snake animation
    if snake_progress > 0:
        _draw_snake(d, snake_progress, state.percent, line_width=line_width)

    # Battery icon (shifted by PAD)
    _draw_battery_icon(d, PAD + ICON_CX, PAD + H // 2,
                       state.percent, state.is_charging, color)

    # Text
    font_title = _find_font(_FONTS_BOLD, 17)
    font_sub   = _find_font(_FONTS_REG,  12)
    d.text((PAD + PAD_LEFT, PAD + H // 2 - 16), state.HUD_title,
           font=font_title, fill=(240, 240, 240))
    d.text((PAD + PAD_LEFT, PAD + H // 2 + 4),  state.HUD_subtitle,
           font=font_sub,   fill=(150, 150, 150))

    return img


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
        self._alpha       = _WIN_ALPHA
        self._preview_speed: Optional[int] = None
        self._preview_lw:    Optional[int] = None

    # ── Public API ───────────────────────────────────────────────────────────

    def show(self, state: BatteryState) -> None:
        self._preview_speed = None
        self._preview_lw    = None
        self._root.after(0, lambda: self._show(state))

    def preview_show(self, state: BatteryState,
                     snake_speed: int = None, line_width: int = None) -> None:
        self._preview_speed = snake_speed
        self._preview_lw    = line_width
        self._root.after(0, lambda: self._show(state))

    def hide(self) -> None:
        self._root.after(0, self._destroy)

    # ── Config helpers ───────────────────────────────────────────────────────

    def _hud_cfg(self) -> dict:
        return self._config.data.get("hud", {}) if self._config else {}

    def _calc_pos(self) -> tuple[int, int]:
        cfg    = self._hud_cfg()
        pos_v  = cfg.get("position_v", "top")
        pos_h  = cfg.get("position_h", "center")
        margin = 32
        sw     = self._root.winfo_screenwidth()
        sh     = self._root.winfo_screenheight()

        # Position of the pill centre (window is CW x CH, offset by PAD)
        x = margin - PAD if pos_h == "left" \
            else sw - CW - margin + PAD if pos_h == "right" \
            else (sw - CW) // 2
        y = margin - PAD if pos_v == "top" \
            else sh - CH - 52 + PAD if pos_v == "bottom" \
            else (sh - CH) // 2
        return x, y

    # ── Internal ─────────────────────────────────────────────────────────────

    def _show(self, state: BatteryState) -> None:
        self._destroy()

        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=_WIN_BG)
        win.attributes("-alpha", _WIN_ALPHA)

        self._win   = win
        self._alpha = _WIN_ALPHA
        self._label = None

        self._redraw(state)
        x, y = self._calc_pos()
        win.geometry(f"{CW}x{CH}+{x}+{y}")

        anim        = self._hud_cfg().get("animation", "bounce")
        snake_delay = 0
        if anim == "fade":
            win.attributes("-alpha", 0.0)
            self._anim_fade_in()
        elif anim == "bounce":
            self._anim_bounce(x, y)
            snake_delay = 380
        self._root.after(snake_delay, lambda: self._anim_snake(state))

        self._schedule_dismiss()

    def _redraw(self, state: BatteryState, snake_progress: float = 0.0) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        gc = self._config.data.get("glow", {}) if self._config else {}
        lw = self._preview_lw if self._preview_lw is not None \
             else int(gc.get("line_width", 4))
        img = make_pill_image(state, snake_progress=snake_progress, line_width=lw)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        if self._label and self._label.winfo_exists():
            self._label.configure(image=self._photo)
        else:
            self._label = tk.Label(self._win, image=self._photo,
                                   bg=_WIN_BG, borderwidth=0)
            self._label.pack()

    # ── Animations ───────────────────────────────────────────────────────────

    def _anim_fade_in(self, step: int = 0, steps: int = 15) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        self._win.attributes("-alpha", _WIN_ALPHA * (step + 1) / steps)
        if step < steps - 1:
            self._root.after(16, lambda: self._anim_fade_in(step + 1, steps))

    def _anim_bounce(self, tx: int, ty: int, steps: int = 22) -> None:
        pos_v   = self._hud_cfg().get("position_v", "top")
        sh      = self._root.winfo_screenheight()
        start_y = sh + CH if pos_v == "bottom" else -CH

        def _ease(t: float) -> float:
            c1, c3 = 1.70158, 2.70158
            return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

        def _step(i: int) -> None:
            if not self._win or not self._win.winfo_exists():
                return
            y = int(start_y + (ty - start_y) * _ease((i + 1) / steps))
            self._win.geometry(f"+{tx}+{y}")
            if i < steps - 1:
                self._root.after(16, lambda: _step(i + 1))

        _step(0)

    def _anim_snake(self, state: BatteryState,
                    step: int = 0, steps: int = 0) -> None:
        if steps == 0:
            gc    = self._config.data.get("glow", {}) if self._config else {}
            speed = self._preview_speed if self._preview_speed is not None \
                    else gc.get("snake_speed", 600)
            perim = _pill_perim(W, H, R)
            steps = max(20, min(120, int(perim / speed * 1000 / 16)))
        if not self._win or not self._win.winfo_exists():
            return
        t = (step + 1) / steps
        self._redraw(state, snake_progress=1 - (1 - t) ** 2)
        if step < steps - 1:
            self._root.after(16, lambda: self._anim_snake(state, step + 1, steps))

    # ── Dismiss / fade-out ────────────────────────────────────────────────────

    def _schedule_dismiss(self) -> None:
        if self._dismiss_id:
            self._root.after_cancel(self._dismiss_id)
        self._dismiss_id = self._root.after(self.DISMISS_MS, self._start_fade)

    def _start_fade(self) -> None:
        self._fade_step(self.FADE_STEPS)

    def _fade_step(self, steps_left: int) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        if steps_left <= 0:
            self._destroy()
            return
        try:
            self._win.attributes("-alpha", _WIN_ALPHA * steps_left / self.FADE_STEPS)
        except Exception:
            pass
        self._root.after(self.FADE_MS, lambda: self._fade_step(steps_left - 1))

    def _destroy(self) -> None:
        if self._dismiss_id:
            self._root.after_cancel(self._dismiss_id)
            self._dismiss_id = None
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win   = None
        self._label = None


# ── BatteryState display helpers ───────────────────────────────────────────────

def hud_title(state: BatteryState) -> str:
    if not state.has_battery:
        return "No Battery"
    if state.is_full:
        return "Fully Charged"
    if state.is_charging:
        return f"Charging — {state.percent}%"
    return f"{state.percent}% Remaining"


def hud_subtitle(state: BatteryState) -> str:
    if not state.has_battery:
        return "No battery detected"
    if state.is_full:
        return "Battery is full"
    if not state.is_charging and state.percent <= 5:
        return "Connect charger immediately"
    if state.seconds_remaining is None:
        return "Calculating..."
    label = "until full" if state.is_charging else "until empty"
    return f"{state.time_remaining_text} {label}"


BatteryState.HUD_title    = property(hud_title)
BatteryState.HUD_subtitle = property(hud_subtitle)
