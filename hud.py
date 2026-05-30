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


# ── Status color ───────────────────────────────────────────────────────────────

def _status_color(state: BatteryState) -> tuple[int, int, int]:
    if state.is_charging or state.is_full:
        return (0, 204, 0)
    if state.percent <= 10:
        return (210, 40, 40)
    if state.percent <= 20:
        return (255, 140, 0)
    return (140, 140, 140)


# ── Pill image renderer ────────────────────────────────────────────────────────

_CHROMA     = (1, 1, 1)
_CHROMA_HEX = "#010101"

W, H, R = 340, 76, 38
BORDER   = 3
ICON_CX  = 24
PAD_LEFT = 52


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


def make_pill_image(state: BatteryState, fill_progress: float = 1.0) -> Image.Image:
    color = _status_color(state)

    img = Image.new("RGBA", (W, H), (*_CHROMA, 255))
    d   = ImageDraw.Draw(img)

    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=(18, 18, 18, 235))
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R,
                         outline=(55, 55, 55, 180), width=BORDER)

    # Animated charge bar at bottom (fill animation)
    if fill_progress < 1.0:
        target = 1.0 if (state.is_charging or state.is_full) else state.percent / 100.0
        bar_w  = int((W - 16) * target * fill_progress)
        if bar_w > 0:
            d.rounded_rectangle([8, H - 7, 8 + bar_w, H - 3],
                                 radius=2, fill=(*color, 200))
    else:
        # Static subtle bar when not animating
        target = 1.0 if (state.is_charging or state.is_full) else state.percent / 100.0
        bar_w  = int((W - 16) * target)
        if bar_w > 0:
            d.rounded_rectangle([8, H - 7, 8 + bar_w, H - 3],
                                 radius=2, fill=(*color, 120))

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
        self._win:        Optional[tk.Toplevel]   = None
        self._label:      Optional[tk.Label]       = None
        self._photo:      Optional[tk.PhotoImage]  = None
        self._dismiss_id: Optional[str]            = None
        self._alpha = 1.0

    # ── Public API ───────────────────────────────────────────────────────────

    def show(self, state: BatteryState) -> None:
        self._root.after(0, lambda: self._show(state))

    def hide(self) -> None:
        self._root.after(0, self._destroy)

    # ── Config helpers ───────────────────────────────────────────────────────

    def _hud_cfg(self) -> dict:
        if self._config:
            return self._config.data.get("hud", {})
        return {}

    def _calc_pos(self) -> tuple[int, int]:
        cfg    = self._hud_cfg()
        pos_v  = cfg.get("position_v", "top")
        pos_h  = cfg.get("position_h", "center")
        margin = 40

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()

        if pos_h == "left":
            x = margin
        elif pos_h == "right":
            x = sw - W - margin
        else:
            x = (sw - W) // 2

        if pos_v == "top":
            y = margin
        elif pos_v == "bottom":
            y = sh - H - 60
        else:
            y = (sh - H) // 2

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

        self._redraw(state, fill_progress=1.0)

        x, y = self._calc_pos()
        win.geometry(f"{W}x{H}+{x}+{y}")

        anim = self._hud_cfg().get("animation", "bounce")
        if anim == "fade":
            win.attributes("-alpha", 0.0)
            self._anim_fade_in(steps=15)
        elif anim == "bounce":
            self._anim_bounce(x, y)
        elif anim == "fill":
            self._anim_fill(state, steps=24)

        self._schedule_dismiss()

    def _redraw(self, state: BatteryState, fill_progress: float = 1.0) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        img = make_pill_image(state, fill_progress=fill_progress)
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

    def _anim_bounce(self, target_x: int, target_y: int, steps: int = 22) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        pos_v  = self._hud_cfg().get("position_v", "top")
        sh     = self._root.winfo_screenheight()
        start_y = sh + H if pos_v == "bottom" else -H

        def _ease_out_back(t: float) -> float:
            c1 = 1.70158
            c3 = c1 + 1
            return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

        def _step(i: int) -> None:
            if not self._win or not self._win.winfo_exists():
                return
            t = _ease_out_back((i + 1) / steps)
            y = int(start_y + (target_y - start_y) * t)
            self._win.geometry(f"+{target_x}+{y}")
            if i < steps - 1:
                self._root.after(16, lambda: _step(i + 1))

        _step(0)

    def _anim_fill(self, state: BatteryState, step: int = 0, steps: int = 24) -> None:
        if not self._win or not self._win.winfo_exists():
            return
        t        = (step + 1) / steps
        progress = 1 - (1 - t) ** 3   # ease-out cubic
        self._redraw(state, fill_progress=progress)
        if step < steps - 1:
            self._root.after(18, lambda: self._anim_fill(state, step + 1, steps))

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
        self._alpha = steps_left / self.FADE_STEPS
        try:
            self._win.attributes("-alpha", self._alpha)
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
