"""Floating pill HUD overlay — shown on battery state changes.

Renders via PIL into a frameless, near-transparent tkinter window.
The pill has a colored border that fills left→right based on battery level.
"""

import os
import tkinter as tk
from dataclasses import dataclass
from typing import Optional

import base64
import io

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

_CHROMA = (1, 1, 1)   # near-black chroma key colour (used for transparency)
_CHROMA_HEX = "#010101"

W, H, R = 340, 76, 38   # pill width, height, corner radius
BORDER = 3               # border stroke width
ICON_CX = 24             # battery icon centre-x
PAD_LEFT = 52            # text left edge


def _draw_battery_icon(d: ImageDraw.ImageDraw, cx: int, cy: int,
                        percent: int, is_charging: bool,
                        color: tuple[int, int, int]) -> None:
    bw, bh = 26, 13
    x1, y1 = cx - bw // 2, cy - bh // 2
    x2, y2 = x1 + bw, y1 + bh
    c = (*color, 255)

    d.rectangle([x2, cy - 3, x2 + 3, cy + 3], fill=c)       # terminal nub
    d.rectangle([x1, y1, x2, y2], outline=c, width=2)         # body outline

    fill_w = int((bw - 4) * percent / 100)
    if fill_w > 0:
        d.rectangle([x1 + 2, y1 + 2, x1 + 2 + fill_w, y2 - 2], fill=c)

    if is_charging:
        bx = cx
        bolt = [(bx + 1, y1 + 1), (bx - 4, cy), (bx, cy),
                (bx - 1, y2 - 1), (bx + 5, cy), (bx + 1, cy)]
        d.polygon(bolt, fill=(255, 240, 60, 255))


def make_pill_image(state: BatteryState) -> Image.Image:
    color = _status_color(state)
    progress = 1.0 if (state.is_charging or state.is_full) else state.percent / 100.0

    # Base image (RGBA, chroma-key background)
    img = Image.new("RGBA", (W, H), (*_CHROMA, 255))
    d = ImageDraw.Draw(img)

    # 1 · Dark pill background
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=(18, 18, 18, 235))

    # 2 · Progress track (full pill, dark border)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R,
                         outline=(45, 45, 45, 255), width=BORDER)

    # 3 · Colored progress border (clipped to progress%)
    clip_w = max(1, int(W * progress))
    border_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(border_layer)
    bd.rounded_rectangle([0, 0, W - 1, H - 1], radius=R,
                          outline=(*color, 255), width=BORDER)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([0, 0, clip_w, H], fill=255)
    border_layer.putalpha(mask)
    img = Image.alpha_composite(img, border_layer)
    d = ImageDraw.Draw(img)

    # 4 · Battery icon
    _draw_battery_icon(d, ICON_CX, H // 2, state.percent,
                       state.is_charging, color)

    # 5 · Title text
    font_title = _find_font(_FONTS_BOLD, 17)
    font_sub   = _find_font(_FONTS_REG, 12)

    title = state.HUD_title
    sub   = state.HUD_subtitle
    d.text((PAD_LEFT, H // 2 - 16), title, font=font_title,
           fill=(255, 255, 255, 255))
    d.text((PAD_LEFT, H // 2 + 4), sub, font=font_sub,
           fill=(160, 160, 160, 255))

    return img


# ── HUD window ─────────────────────────────────────────────────────────────────

class HudOverlay:
    """Shows/hides the floating pill on the main tkinter thread."""

    DISMISS_MS = 4000   # ms before auto-dismiss
    FADE_STEPS = 20     # fade-out steps
    FADE_MS    = 25     # ms between fade steps

    def __init__(self, root: tk.Tk):
        self._root = root
        self._win: Optional[tk.Toplevel] = None
        self._photo: Optional[tk.PhotoImage] = None
        self._dismiss_id: Optional[str] = None
        self._alpha = 1.0

    # ── Public API (thread-safe via root.after) ──────────────────────────────

    def show(self, state: BatteryState) -> None:
        self._root.after(0, lambda: self._show(state))

    def hide(self) -> None:
        self._root.after(0, self._destroy)

    # ── Internal (main thread only) ──────────────────────────────────────────

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

        img = make_pill_image(state)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))

        lbl = tk.Label(win, image=self._photo, bg=_CHROMA_HEX, borderwidth=0)
        lbl.pack()

        sw = win.winfo_screenwidth()
        win.geometry(f"{W}x{H}+{(sw - W) // 2}+60")

        self._win = win
        self._alpha = 1.0
        self._schedule_dismiss()

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
        self._root.after(self.FADE_MS,
                         lambda: self._fade_step(steps_left - 1))

    def _destroy(self) -> None:
        if self._dismiss_id:
            self._root.after_cancel(self._dismiss_id)
            self._dismiss_id = None
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None


# ── BatteryState display helpers (monkey-patch style) ─────────────────────────
# Attach HUD-specific text properties to BatteryState via extension functions.

def hud_title(state: BatteryState) -> str:
    if not state.has_battery:
        return "No Battery"
    if state.is_full:
        return "Fully Charged"
    if state.is_charging:
        return f"{state.percent}% Charged"
    return f"{state.percent}% Remaining"


def hud_subtitle(state: BatteryState) -> str:
    if not state.has_battery:
        return "No battery detected"
    if state.is_full:
        return "Battery is full"
    if not state.has_battery:
        return ""
    if not state.is_charging and state.percent <= 5:
        return "Connect charger immediately"
    if state.seconds_remaining is None:
        return "Calculating..."
    label = "until full" if state.is_charging else "until empty"
    return f"{state.time_remaining_text} {label}"


# Attach as properties (used in make_pill_image above)
BatteryState.HUD_title    = property(hud_title)
BatteryState.HUD_subtitle = property(hud_subtitle)
