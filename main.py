#!/usr/bin/env python3
"""Watt — System tray battery monitor for Windows and Ubuntu 24.04 LTS."""

import logging
import queue
import threading
import time
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw
from sni_tray import SNITray

from alerts import AlertManager
import i18n
from i18n import t
from battery import BatteryState, get_battery_state
from config import ConfigManager
from hud import HudOverlay, charge_color
from notifier import send_notification
from popup import BatteryPopup
from screen_glow import ScreenGlow
from settings_window import SettingsWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("watt")

# ── App state ──────────────────────────────────────────────────────────────────

_config = ConfigManager()
i18n.set_lang(_config.data.get("language", "en"))
_alerts = AlertManager(_config)
_state: BatteryState = BatteryState()
_state_lock = threading.Lock()

_tray: Optional[SNITray] = None
_root: Optional[tk.Tk] = None
_hud: Optional[HudOverlay] = None
_glow: Optional[ScreenGlow] = None
_popup: Optional[tk.Toplevel] = None
_settings_win: Optional[SettingsWindow] = None
_popup_opened_at: float = 0.0   # timestamp of last popup open
_icon_center: tuple[int, int] = (0, 0)  # last known tray icon screen position
_hover_was_near: bool = False
_hover_close_ticks: int = 0

# Thread-safe queue for cross-thread popup requests
_popup_queue: queue.Queue = queue.Queue()


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


APP_VERSION = "v1.4.0"

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
            for title, msg, level in fired:
                # HUD is the primary alert notification
                if _hud:
                    _hud.show_alert(new, level, title, msg)
                # Screen glow for low battery
                if (_config.data.get("alerts", {}).get("glow_on_low", True)
                        and not new.is_charging and _glow):
                    color = (220, 30, 20) if level == "critical" else (210, 110, 0)
                    _glow.show(color)
                # Keep system notification as fallback
                send_notification(title, msg)

            # Tray icon + tooltip
            if _tray:
                _tray.set_icon(make_tray_icon(new))
                _tray.set_title(t("tray.title", pct=new.percent, status=new.status_text)
                                if new.has_battery else t("tray.no_battery"))

            # HUD overlay for charging-state changes (non-alert)
            if not fired and _should_show_hud(new, _prev_state) and _hud:
                _hud.show(new)

            with _state_lock:
                _state = new
            _prev_state = new

        except Exception as e:
            logger.error(f"Poll error: {e}", exc_info=True)

        time.sleep(_config.data.get("poll_interval", 30))


def _watch_charging() -> None:
    """Fast loop (2s) that detects charger plug/unplug and triggers glow + HUD.

    Debounced: state must be stable for 2 consecutive reads before triggering,
    preventing repeated notifications from hardware reporting fluctuations.
    """
    confirmed: Optional[bool] = None   # last confirmed stable state
    candidate: Optional[bool] = None   # state seen in last read
    candidate_count: int = 0

    while True:
        try:
            s = get_battery_state()

            if s.is_charging == candidate:
                candidate_count += 1
            else:
                candidate       = s.is_charging
                candidate_count = 1

            if candidate_count >= 2 and candidate != confirmed:
                confirmed = candidate
                logger.info("Charging state stable → is_charging=%s", confirmed)
                if _glow:
                    if confirmed:
                        _glow.show(charge_color(s.percent))
                    else:
                        _glow.hide()
                if confirmed and _hud:
                    _hud._launch(s)

        except Exception:
            logger.exception("_watch_charging error")
        time.sleep(2)


# ── Tray callbacks ─────────────────────────────────────────────────────────────


def _show_popup(icon_x: int = 0, icon_y: int = 0,
                from_hover: bool = False) -> None:
    global _popup, _popup_opened_at, _icon_center
    now = time.time()
    if icon_x and icon_y:
        old = _icon_center
        _icon_center = (icon_x, icon_y)
        if abs(old[0] - icon_x) > 5 or abs(old[1] - icon_y) > 5:
            _config.data["_tray_icon_pos"] = [icon_x, icon_y]
            _config.save()
    if _popup and _popup.winfo_exists():
        return  # already open — hover or click keeps it open
    with _state_lock:
        state = _state
    x = icon_x or (_root.winfo_pointerx() if _root else 0)
    y = icon_y or (_root.winfo_pointery() if _root else 0)

    def _current_state():
        with _state_lock:
            return _state

    _popup = BatteryPopup(_root, state, click_x=x, click_y=y,
                          on_settings=_on_settings, on_quit=_on_quit,
                          app_version=APP_VERSION,
                          state_fn=_current_state,
                          from_hover=from_hover)
    _popup_opened_at = now


def _hover_loop() -> None:
    """Poll mouse position; open popup on hover over icon, close when mouse wanders away."""
    global _hover_was_near, _hover_close_ticks, _popup
    try:
        if _root:
            mx = _root.winfo_pointerx()
            my = _root.winfo_pointery()

            near_icon = False
            if _icon_center != (0, 0):
                ix, iy = _icon_center
                # Match only the icon itself: ±18px vertically (panel height),
                # ±18px horizontally (icon width ~22px logical at up to 200% HiDPI)
                near_icon = abs(my - iy) <= 18 and abs(mx - ix) <= 18
                if near_icon != _hover_was_near:
                    logger.info("hover state: near=%s mouse=(%d,%d) icon=(%d,%d)",
                                near_icon, mx, my, ix, iy)
                if near_icon and not _hover_was_near:
                    if not (_popup and _popup.winfo_exists()):
                        _show_popup(ix, iy, from_hover=True)
                _hover_was_near = near_icon

            # Auto-close after ~500ms when mouse is away from both icon and popup
            if _popup and _popup.winfo_exists():
                try:
                    px, py = _popup.winfo_x(), _popup.winfo_y()
                    pw, ph = _popup.winfo_width(), _popup.winfo_height()
                    in_popup = (px - 20 <= mx <= px + pw + 20 and
                                py - 6 <= my <= py + ph + 20)
                    if not near_icon and not in_popup:
                        _hover_close_ticks += 1
                        if _hover_close_ticks >= 8:   # 8 × 120ms ≈ 1s
                            _popup.destroy()
                            _popup = None
                            _hover_close_ticks = 0
                    else:
                        _hover_close_ticks = 0
                except Exception:
                    _hover_close_ticks = 0
    except Exception:
        pass
    if _root:
        _root.after(120, _hover_loop)


def _on_settings(_icon=None, _item=None) -> None:
    _root.after(0, _open_settings)


def _open_settings() -> None:
    global _settings_win
    if _settings_win and _settings_win.winfo_exists():
        _settings_win.lift()
        return

    def _hud_preview(speed: int, lw_pct: int, anim_speed: float) -> None:
        if not _hud or not _settings_win: return
        hud_cfg = _config.data.setdefault("hud", {})
        hud_cfg["anim_speed"]   = anim_speed
        hud_cfg["animation"]    = _settings_win._v_anim.get()
        hud_cfg["bg_lightness"] = _settings_win._v_bg_light.get()
        hud_cfg["win_alpha"]    = _settings_win._v_win_alpha.get()
        with _state_lock: s = _state
        _hud.preview_show(s, snake_speed=speed, line_width_pct=lw_pct)

    def _pos_preview() -> None:
        if not _hud: return
        with _state_lock: s = _state
        _hud.preview_show(s)

    def _glow_preview(cfg: dict) -> None:
        if _glow: _glow.preview(cfg)

    _settings_win = SettingsWindow(
        _root, _config,
        on_save=lambda: _alerts.reset(),
        on_preview=_glow_preview,
        on_hud_preview=_hud_preview,
        on_pos_preview=_pos_preview,
    )


def _on_quit(_icon=None, _item=None) -> None:
    if _tray:
        _tray.stop()
    _root.after(0, _root.quit)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global _tray, _root, _hud, _glow, _state, _prev_state, _icon_center

    _state = get_battery_state()
    _prev_state = _state   # prevents first poll from re-triggering glow

    _root = tk.Tk()
    _root.withdraw()
    _root.title("Watt")

    # Restore last known tray icon position so hover works immediately on re-launch
    saved = _config.data.get("_tray_icon_pos", [0, 0])
    if saved[0] and saved[1]:
        _icon_center = (int(saved[0]), int(saved[1]))
        logger.info("Restored tray icon position: %s", _icon_center)

    _hud  = HudOverlay(_root, _config)
    _glow = ScreenGlow(_root, _config)

    _tray = SNITray(
        "watt",
        title="Watt — Battery Monitor",
        on_activate=lambda x, y: _popup_queue.put((x, y)),
        on_context=lambda x, y:  _popup_queue.put((x, y)),
    )
    _tray.set_icon(make_tray_icon(_state))

    def _drain_popup_queue():
        try:
            while True:
                x, y = _popup_queue.get_nowait()
                try:
                    _show_popup(x, y)
                except Exception:
                    logger.exception("_show_popup error")
        except queue.Empty:
            pass
        _root.after(50, _drain_popup_queue)

    _root.after(50, _drain_popup_queue)
    _root.after(500, _hover_loop)

    threading.Thread(target=_poll,            daemon=True).start()
    threading.Thread(target=_watch_charging,  daemon=True).start()
    threading.Thread(target=_tray.run,        daemon=True).start()

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
