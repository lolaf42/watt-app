"""Floating pill HUD overlay — shown on battery state changes."""

import base64
import io
import math
import os
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

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


# ── Color scheme (shared with main.py via import) ─────────────────────────────

def charge_color(percent: int) -> tuple[int, int, int]:
    """Border/glow color based on battery charge level."""
    if percent >= 60:
        return (0, 200, 60)    # green
    if percent >= 25:
        return (255, 140, 0)   # orange
    if percent >= 10:
        return (220, 70, 0)    # dark orange
    return (200, 30, 30)       # red


def _status_color(state: BatteryState) -> tuple[int, int, int]:
    """Icon/text accent color."""
    if state.is_charging or state.is_full:
        return (0, 204, 0)
    return charge_color(state.percent)


# ── Pill image renderer ────────────────────────────────────────────────────────

_CHROMA     = (1, 1, 1)
_CHROMA_HEX = "#010101"

W, H, R = 340, 76, 38
BORDER   = 3
ICON_CX  = 24
PAD_LEFT = 52


# ── Perimeter math (same convention as glow_worker) ───────────────────────────

def _pill_perim(gw: int, gh: int, gr: int) -> float:
    return 2 * (gw - 2 * gr) + 2 * math.pi * gr


def _pill_xy(dist: float, gw: int, gh: int, gr: int) -> tuple[float, float]:
    """Perimeter distance → (x, y), clockwise from left-centre going up."""
    perim = _pill_perim(gw, gh, gr)
    d     = dist % perim
    aq    = math.pi * gr / 2
    st    = gw - 2 * gr

    if d < aq:
        t = math.pi * (1 - d / aq * 0.5)
        return gr + gr * math.cos(t), gr - gr * math.sin(t)
    d -= aq
    if d < st:
        return gr + d, 0.0
    d -= st
    if d < aq:
        t = math.pi / 2 * (1 - d / aq)
        return gw - gr + gr * math.cos(t), gr - gr * math.sin(t)
    d -= aq
    if d < aq:
        t = -math.pi / 2 * d / aq
        return gw - gr + gr * math.cos(t), gr - gr * math.sin(t)
    d -= aq
    if d < st:
        return gw - gr - d, float(gh)
    d -= st
    frac = min(d / aq, 1.0)
    t = -math.pi / 2 * (1 + frac)
    return gr + gr * math.cos(t), gr - gr * math.sin(t)


def _border_pts(target_dist: float, n: int = 400) -> list[tuple[float, float]]:
    perim = _pill_perim(W, H, R)
    pts: list[tuple[float, float]] = []
    for i in range(n + 1):
        dist = perim * i / n
        if dist > target_dist:
            break
        pts.append(_pill_xy(dist, W, H, R))
    return pts


def _draw_charge_border(d: ImageDraw.ImageDraw, percent: int) -> None:
    """Static partial border arc showing charge level."""
    if percent <= 0:
        return
    color  = charge_color(percent)
    perim  = _pill_perim(W, H, R)
    target = perim * min(percent, 100) / 100
    pts    = _border_pts(target)
    if len(pts) >= 2:
        d.line(pts, fill=(*color, 180), width=4)


def _draw_snake(d: ImageDraw.ImageDraw, snake_progress: float,
                percent: int, line_width: int = 4) -> None:
    """Animated snake growing from 0 to full perimeter, drawn over charge border."""
    if snake_progress <= 0:
        return
    color  = charge_color(percent)
    bright = tuple(min(c + 60, 255) for c in color)
    perim  = _pill_perim(W, H, R)
    target = perim * min(snake_progress, 1.0)
    pts    = _border_pts(target)
    if len(pts) < 2:
        return
    d.line(pts, fill=(*color, 50),  width=line_width * 3)  # outer glow
    d.line(pts, fill=(*color, 220), width=line_width)       # core
    hx, hy = pts[-1]
    r = max(2, line_width // 2 + 1)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=(*bright, 255))


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

    img = Image.new("RGBA", (W, H), (*_CHROMA, 255))
    d   = ImageDraw.Draw(img)

    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=(18, 18, 18, 235))
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R,
                         outline=(45, 45, 45, 160), width=BORDER)

    _draw_charge_border(d, state.percent)

    if snake_progress > 0:
        _draw_snake(d, snake_progress, state.percent, line_width=line_width)

    _draw_battery_icon(d, ICON_CX, H // 2, state.percent, state.is_charging, color)

    font_title = _find_font(_FONTS_BOLD, 17)
    font_sub   = _find_font(_FONTS_REG, 12)
    d.text((PAD_LEFT, H // 2 - 16), state.HUD_title, font=font_title,
           fill=(255, 255, 255, 255))
    d.text((PAD_LEFT, H // 2 + 4),  state.HUD_subtitle, font=font_sub,
           fill=(160, 160, 160, 255))

    return img


# ── HUD window ─────────────────────────────────────────────────────────────────

class HudOverlay:
    DISMISS_MS = 4000
    FADE_STEPS = 20
    FADE_MS    = 25

    def __init__(self, root: tk.Tk, config=None):
        self._root   = root
        self._config = config
        self._win:        Optional[tk.Toplevel]  = None
        self._label:      Optional[tk.Label]     = None
        self._photo:      Optional[tk.PhotoImage] = None
        self._dismiss_id: Optional[str]          = None
        self._alpha = 1.0

    # ── Public API ───────────────────────────────────────────────────────────

    def show(self, state: BatteryState) -> None:
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
        margin = 40
        sw     = self._root.winfo_screenwidth()
        sh     = self._root.winfo_screenheight()

        x = margin if pos_h == "left" else sw - W - margin if pos_h == "right" else (sw - W) // 2
        y = margin if pos_v == "top"  else sh - H - 60    if pos_v == "bottom" else (sh - H) // 2
        return x, y

    # ── Internal ─────────────────────────────────────────────────────────────

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

        self._win   = win
        self._alpha = 1.0
        self._label = None

        self._redraw(state)
        x, y = self._calc_pos()
        win.geometry(f"{W}x{H}+{x}+{y}")

        anim = self._hud_cfg().get("animation", "bounce")
        snake_delay = 0
        if anim == "fade":
            win.attributes("-alpha", 0.0)
            self._anim_fade_in()
        elif anim == "bounce":
            self._anim_bounce(x, y)
            snake_delay = 380   # wait for bounce to finish
        # Snake always runs after the position animation
        self._root.after(snake_delay, lambda: self._anim_snake(state))

        self._schedule_dismiss()

    def _redraw(self, state: BatteryState, snake_progress: float = 0.0) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        gc = self._config.data.get("glow", {}) if self._config else {}
        lw = int(gc.get("line_width", 4))
        img = make_pill_image(state, snake_progress=snake_progress, line_width=lw)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        if self._label and self._label.winfo_exists():
            self._label.configure(image=self._photo)
        else:
            self._label = tk.Label(self._win, image=self._photo,
                                   bg=_CHROMA_HEX, borderwidth=0)
            self._label.pack()

    # ── Animations ───────────────────────────────────────────────────────────

    def _anim_fade_in(self, step: int = 0, steps: int = 15) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        self._win.attributes("-alpha", (step + 1) / steps)
        if step < steps - 1:
            self._root.after(16, lambda: self._anim_fade_in(step + 1, steps))

    def _anim_bounce(self, tx: int, ty: int, steps: int = 22) -> None:
        pos_v   = self._hud_cfg().get("position_v", "top")
        sh      = self._root.winfo_screenheight()
        start_y = sh + H if pos_v == "bottom" else -H

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
        """Snake grows from 0 to full perimeter, speed from config."""
        if steps == 0:
            gc    = self._config.data.get("glow", {}) if self._config else {}
            speed = gc.get("snake_speed", 600)          # px/s
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
            self._win.attributes("-alpha", steps_left / self.FADE_STEPS)
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
