#!/usr/bin/env python3
"""Watt — System tray battery monitor for Windows and Ubuntu 24.04 LTS."""

import logging
import threading
import time
import tkinter as tk
from typing import Optional

import pystray
from PIL import Image, ImageDraw

from alerts import AlertManager
from battery import BatteryState, get_battery_state
from config import ConfigManager
from hud import HudOverlay, charge_color
from notifier import send_notification
from screen_glow import ScreenGlow
from settings_window import SettingsWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("watt")

# ── App state ──────────────────────────────────────────────────────────────────

_config = ConfigManager()
_alerts = AlertManager(_config)
_state: BatteryState = BatteryState()
_state_lock = threading.Lock()

_tray: Optional[pystray.Icon] = None
_root: Optional[tk.Tk] = None
_hud: Optional[HudOverlay] = None
_glow: Optional[ScreenGlow] = None
_popup: Optional[tk.Toplevel] = None
_settings_win: Optional[SettingsWindow] = None


# ── Tray icon generation ───────────────────────────────────────────────────────

def _level_color(state: BatteryState) -> tuple[int, int, int]:
    if not state.has_battery:
        return (100, 100, 100)
    if state.is_charging or state.is_full:
        return (40, 200, 40)
    if state.percent <= 20:
        return (210, 40, 40)
    if state.percent <= 50:
        return (255, 160, 0)
    return (40, 200, 40)


def make_tray_icon(state: BatteryState) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    color = _level_color(state)
    outline = (210, 210, 210, 255)

    bx1, by1, bx2, by2 = 4, 20, 50, 44
    d.rectangle([50, 27, 60, 37], fill=outline)
    for i in range(3):
        d.rectangle([bx1 + i, by1 + i, bx2 - i, by2 - i], outline=outline)

    if state.has_battery:
        fill_w = int((bx2 - bx1 - 6) * state.percent / 100)
        if fill_w > 0:
            d.rectangle([bx1 + 3, by1 + 3, bx1 + 3 + fill_w, by2 - 3],
                        fill=(*color, 255))

    if state.is_charging:
        cx = (bx1 + bx2) // 2
        cy = (by1 + by2) // 2
        bolt = [(cx + 2, by1 + 4), (cx - 5, cy + 1), (cx, cy + 1),
                (cx - 2, by2 - 4), (cx + 6, cy - 1), (cx + 1, cy - 1)]
        d.polygon(bolt, fill=(255, 240, 50, 230))

    return img


# ── Battery popup window ───────────────────────────────────────────────────────

_BG  = "#0D1117"
_BG2 = "#161B22"
_SEP = "#21262D"
_FG  = "#C9D1D9"
_DIM = "#8B949E"


class BatteryPopup(tk.Toplevel):

    def __init__(self, parent: tk.Tk, state: BatteryState):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=_BG)
        self.resizable(False, False)
        self._build(state)
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        self.geometry(f"+{sw - w - 14}+{sh - h - 56}")
        self.bind("<FocusOut>", lambda _e: self.destroy())
        self.focus_force()

    def _sep(self) -> None:
        tk.Frame(self, bg=_SEP, height=1).pack(fill="x", pady=3)

    def _section(self, icon: str, title: str, color: str) -> tk.Frame:
        f = tk.Frame(self, bg=_BG2)
        f.pack(fill="x", padx=10, pady=3)
        tk.Label(f, text=f"{icon}  {title}", bg=_BG2, fg=color,
                 font=("Segoe UI", 11, "bold"), anchor="w",
                 padx=10, pady=6).pack(fill="x")
        body = tk.Frame(f, bg=_BG2)
        body.pack(fill="x", padx=10, pady=(0, 8))
        return body

    def _row2(self, parent: tk.Frame,
              lbl1: str, val1: str, col1: str,
              lbl2: str, val2: str, col2: str) -> None:
        f = tk.Frame(parent, bg=_BG2)
        f.pack(fill="x", pady=1)
        lc = tk.Frame(f, bg=_BG2)
        lc.pack(side="left", expand=True, fill="x")
        rc = tk.Frame(f, bg=_BG2)
        rc.pack(side="right", expand=True, fill="x")
        tk.Label(lc, text=lbl1, bg=_BG2, fg=_DIM,
                 font=("Segoe UI", 10), anchor="w").pack(anchor="w")
        tk.Label(lc, text=val1, bg=_BG2, fg=col1,
                 font=("Segoe UI", 16, "bold"), anchor="w").pack(anchor="w")
        tk.Label(rc, text=lbl2, bg=_BG2, fg=_DIM,
                 font=("Segoe UI", 10), anchor="e").pack(anchor="e")
        tk.Label(rc, text=val2, bg=_BG2, fg=col2,
                 font=("Segoe UI", 16, "bold"), anchor="e").pack(anchor="e")

    def _row(self, parent: tk.Frame, label: str, value: str,
             val_color: str = _FG) -> None:
        f = tk.Frame(parent, bg=_BG2)
        f.pack(fill="x", pady=1)
        tk.Label(f, text=label, bg=_BG2, fg=_DIM,
                 font=("Segoe UI", 10), anchor="w").pack(side="left")
        tk.Label(f, text=value, bg=_BG2, fg=val_color,
                 font=("Segoe UI", 10, "bold"), anchor="e").pack(side="right")

    def _build(self, s: BatteryState) -> None:
        accent = ("#00CC00" if (s.is_charging or s.is_full)
                  else "#DC3232" if s.percent <= 20
                  else "#FFA000" if s.percent <= 50
                  else "#00CC00")

        # ── Header ────────────────────────────────────────────────────────────
        hf = tk.Frame(self, bg=_BG)
        hf.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(hf, text=f"{s.percent}%" if s.has_battery else "N/A",
                 bg=_BG, fg=accent,
                 font=("Segoe UI", 42, "bold")).pack(side="left")
        rf = tk.Frame(hf, bg=_BG)
        rf.pack(side="right", anchor="s", pady=10)
        icon = "⚡" if s.is_charging else ("🪫" if s.percent <= 10 else "🔋")
        tk.Label(rf, text=f"{icon}  {s.status_text}",
                 bg=_BG, fg=accent, font=("Segoe UI", 13)).pack(anchor="e")
        if s.has_battery and s.seconds_remaining is not None:
            suffix = "until full" if s.is_charging else "remaining"
            tk.Label(rf, text=f"{s.time_remaining_text} {suffix}",
                     bg=_BG, fg=_DIM, font=("Segoe UI", 10)).pack(anchor="e")

        # Progress bar
        import base64, io
        from PIL import Image as PImage, ImageDraw as PDraw
        bar_w = 320
        bar_h = 6
        bar_img = PImage.new("RGB", (bar_w, bar_h), (30, 38, 41))
        if s.has_battery and s.percent > 0:
            r, g, b = (int(accent[1:3], 16),
                       int(accent[3:5], 16),
                       int(accent[5:7], 16))
            fill = int(bar_w * s.percent / 100)
            for x in range(fill):
                for y in range(bar_h):
                    bar_img.putpixel((x, y), (r, g, b))
        buf = io.BytesIO()
        bar_img.save(buf, format="PNG")
        bar_photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        bar_lbl = tk.Label(self, image=bar_photo, bg=_BG, borderwidth=0)
        bar_lbl.image = bar_photo
        bar_lbl.pack(padx=14, pady=(0, 8))

        self._sep()

        # ── Battery Health ────────────────────────────────────────────────────
        if s.health_percent is not None:
            health_color = "#E3B341" if s.health_percent < 80 else "#3FB950"
            body = self._section("⚠" if s.health_percent < 80 else "✔",
                                  "Battery Health", health_color)
            f = tk.Frame(body, bg=_BG2)
            f.pack(fill="x")
            tk.Label(f, text=f"{s.health_percent:.0f}%  {s.health_label}",
                     bg=_BG2, fg=health_color,
                     font=("Segoe UI", 20, "bold")).pack(side="left")
            if s.cycle_count is not None:
                cf = tk.Frame(body, bg=_BG2)
                cf.pack(fill="x", anchor="e")
                tk.Label(cf, text=f"{s.cycle_count:,}", bg=_BG2, fg=_DIM,
                          font=("Segoe UI", 10), anchor="e").pack(side="right")
                tk.Label(cf, text="Cycle Count", bg=_BG2, fg=_DIM,
                          font=("Segoe UI", 9), anchor="e").pack(side="right", padx=4)
            if s.health_percent < 80:
                tk.Label(body, text="Consider servicing your battery",
                         bg=_BG2, fg=_DIM,
                         font=("Segoe UI", 10), anchor="w").pack(anchor="w", pady=(4, 0))

        # ── Temperature ───────────────────────────────────────────────────────
        if s.temperature_celsius is not None:
            temp_color = ("#DC3232" if s.temperature_celsius >= 50
                          else "#FFA000" if s.temperature_celsius >= 40
                          else "#3FB950")
            body = self._section("✔", "Temperature", temp_color)
            f = tk.Frame(body, bg=_BG2)
            f.pack(fill="x")
            lf = tk.Frame(f, bg=_BG2)
            lf.pack(side="left")
            tk.Label(lf, text=f"{s.temperature_celsius:.1f}°C",
                     bg=_BG2, fg=temp_color,
                     font=("Segoe UI", 20, "bold")).pack(anchor="w")
            tk.Label(lf, text=f"{s.temperature_celsius * 9/5 + 32:.1f}°F",
                     bg=_BG2, fg=_DIM, font=("Segoe UI", 10)).pack(anchor="w")
            rf2 = tk.Frame(f, bg=_BG2)
            rf2.pack(side="right", anchor="e")
            tk.Label(rf2, text=s.TemperatureStatus,
                     bg=_BG2, fg=temp_color,
                     font=("Segoe UI", 11, "bold")).pack(anchor="e")
            tk.Label(rf2, text="Optimal performance" if s.temperature_celsius < 40
                     else "High temperature", bg=_BG2, fg=_DIM,
                     font=("Segoe UI", 9)).pack(anchor="e")

        # ── Power & Electrical ────────────────────────────────────────────────
        if s.voltage_mv is not None or s.power_watts is not None:
            body = self._section("⚡", "Power & Electrical", "#3FB950")
            self._row2(body,
                       "Power Usage",
                       f"{s.power_watts:.1f} W" if s.power_watts is not None else "N/A",
                       "#FFFFFF",
                       "Voltage",
                       f"{s.voltage_mv / 1000:.2f} V" if s.voltage_mv else "N/A",
                       "#FFFFFF")
            charge_label = "Charging" if s.is_charging else "Discharging"
            charge_color = "#3FB950" if s.is_charging else _DIM
            self._row2(body,
                       "Current",
                       f"{s.current_ma:,} mA" if s.current_ma else "N/A",
                       "#FFFFFF",
                       charge_label,
                       "Normal voltage",
                       charge_color)

        # ── Capacity Details ──────────────────────────────────────────────────
        if s.remaining_mwh is not None:
            body = self._section("🔋", "Capacity Details", "#58A6FF")
            self._row(body, "Remaining",
                      f"{s.remaining_mwh / 1000:.3f} Wh", "#3FB950")
            if s.full_capacity_mwh:
                self._row(body, "Current Full",
                          f"{s.full_capacity_mwh / 1000:.3f} Wh", "#58A6FF")
            if s.design_capacity_mwh:
                self._row(body, "Design Capacity",
                          f"{s.design_capacity_mwh / 1000:.3f} Wh", _DIM)

        self._sep()

        # ── Footer buttons ────────────────────────────────────────────────────
        for text, cmd, color in [
            ("⚙  Settings...",    _on_settings, _FG),
            ("⏻  Quit Watt",      _on_quit,     "#FF4444"),
        ]:
            btn = tk.Button(self, text=text, command=cmd,
                            bg=_BG, fg=color, relief="flat",
                            font=("Segoe UI", 11), anchor="w",
                            padx=14, pady=8, cursor="hand2",
                            activebackground=_BG2, activeforeground=color)
            btn.pack(fill="x")
            tk.Frame(self, bg=_SEP, height=1).pack(fill="x")


# Add computed display properties to BatteryState
def _temp_status(s: BatteryState) -> str:
    if s.temperature_celsius is None:
        return ""
    if s.temperature_celsius >= 50:
        return "Hot"
    if s.temperature_celsius >= 40:
        return "Warm"
    if s.temperature_celsius >= 25:
        return "Normal"
    return "Cool"

def _power_watts(s: BatteryState) -> Optional[float]:
    return s.PowerWatts if hasattr(s, 'PowerWatts') else None

BatteryState.TemperatureStatus = property(_temp_status)


# ── Polling ────────────────────────────────────────────────────────────────────

_prev_state: Optional[BatteryState] = None


def _should_show_hud(new: BatteryState, old: Optional[BatteryState]) -> bool:
    if not new.has_battery:
        return False
    if old is None:
        return True
    # charging state change handled by _watch_charging (not here)
    if new.is_full and not old.is_full:
        return True
    for t in _config.data.get("thresholds", {}).get("low", []):
        if new.percent <= t < old.percent:
            return True
    for t in _config.data.get("thresholds", {}).get("high", []):
        if new.percent >= t > old.percent:
            return True
    return False


def _poll() -> None:
    global _state, _prev_state
    while True:
        try:
            new = get_battery_state()

            fired = _alerts.check(new)
            for title, msg in fired:
                send_notification(title, msg)

            # Tray icon + tooltip
            if _tray:
                _tray.icon = make_tray_icon(new)
                _tray.title = (f"Watt — {new.percent}% ({new.status_text})"
                               if new.has_battery else "Watt — No battery")

            # HUD overlay
            if _should_show_hud(new, _prev_state) and _hud:
                _hud.show(new)

            with _state_lock:
                _state = new
            _prev_state = new

        except Exception as e:
            logger.error(f"Poll error: {e}", exc_info=True)

        time.sleep(_config.data.get("poll_interval", 30))


def _watch_charging() -> None:
    """Fast loop (2s) that detects charger plug/unplug and triggers glow immediately."""
    prev_charging: Optional[bool] = None
    while True:
        try:
            s = get_battery_state()
            if prev_charging is not None and s.is_charging != prev_charging:
                if _glow:
                    if s.is_charging:
                        _glow.show(charge_color(s.percent))
                    else:
                        _glow.hide()
                if _hud and s.is_charging:
                    _hud.show(s)
            prev_charging = s.is_charging
        except Exception:
            pass
        time.sleep(2)


# ── Tray callbacks ─────────────────────────────────────────────────────────────

def _on_details(_icon=None, _item=None) -> None:
    _root.after(0, _show_popup)


def _show_popup() -> None:
    global _popup
    if _popup and _popup.winfo_exists():
        _popup.destroy()
        _popup = None
        return
    with _state_lock:
        state = _state
    _popup = BatteryPopup(_root, state)


def _on_settings(_icon=None, _item=None) -> None:
    _root.after(0, _open_settings)


def _open_settings() -> None:
    global _settings_win
    if _settings_win and _settings_win.winfo_exists():
        _settings_win.lift()
        return
    _settings_win = SettingsWindow(_root, _config, lambda: _alerts.reset(),
                                   lambda cfg: _glow.preview(cfg))


def _on_quit(_icon=None, _item=None) -> None:
    if _tray:
        _tray.stop()
    _root.after(0, _root.quit)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global _tray, _root, _hud, _glow, _state, _prev_state

    _state = get_battery_state()
    _prev_state = _state   # prevents first poll from re-triggering glow

    _root = tk.Tk()
    _root.withdraw()
    _root.title("Watt")

    _hud  = HudOverlay(_root, _config)
    _glow = ScreenGlow(_root, _config)

    menu = pystray.Menu(
        pystray.MenuItem("Battery Details...", _on_details, default=True),
        pystray.MenuItem("Settings...",        _on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit",               _on_quit),
    )
    _tray = pystray.Icon(
        "watt",
        icon=make_tray_icon(_state),
        title="Watt — Battery Monitor",
        menu=menu,
    )

    threading.Thread(target=_poll,            daemon=True).start()
    threading.Thread(target=_watch_charging,  daemon=True).start()
    threading.Thread(target=_tray.run,        daemon=True).start()

    # Show HUD immediately on startup
    _hud.show(_state)

    # Start glow if already charging on launch
    if _glow and _state.has_battery and _state.is_charging:
        _glow.show(charge_color(_state.percent))

    logger.info("Watt started — %s", _state.status_text)
    try:
        _root.mainloop()
    finally:
        _tray.stop()


if __name__ == "__main__":
    main()
