"""Floating pill HUD — launches hud_worker.py (GTK/Cairo) for real RGBA transparency."""

import json
import os
import subprocess
import sys
import tkinter as tk
from typing import Optional

from battery import BatteryState
from i18n import t

_WORKER = os.path.join(os.path.dirname(__file__), "hud_worker.py")

# Snap-safe env (same pattern as screen_glow.py)
def _clean_env() -> dict:
    env = os.environ.copy()
    _SNAP = {"GTK_PATH","GTK_EXE_PREFIX","GTK_IM_MODULE_FILE",
             "GDK_PIXBUF_MODULE_FILE","GDK_PIXBUF_MODULEDIR",
             "GIO_MODULE_DIR","GSETTINGS_SCHEMA_DIR","SNAP_LIBRARY_PATH"}
    for k in _SNAP:
        env.pop(k, None)
    for k in list(env):
        if env.get(k,"") and "/snap/" in env[k] and k in ("LD_LIBRARY_PATH","LD_PRELOAD"):
            env.pop(k, None)
    # Force X11 backend so Gtk.Window.move() works on XWayland.
    # Without this GTK picks the Wayland backend and silently ignores move().
    env["GDK_BACKEND"] = "x11"
    return env


# ── Colors ─────────────────────────────────────────────────────────────────────

def charge_color(percent: int) -> tuple[int, int, int]:
    if percent >= 60: return (0, 200, 60)
    if percent >= 25: return (255, 140, 0)
    if percent >= 10: return (220, 70, 0)
    return (200, 30, 30)


# ── HUD overlay ────────────────────────────────────────────────────────────────

class HudOverlay:
    def __init__(self, root: tk.Tk, config=None):
        self._root   = root
        self._config = config
        self._proc:  Optional[subprocess.Popen] = None

    # ── Public ─────────────────────────────────────────────────────────────────

    def show(self, state: BatteryState) -> None:
        self._root.after(0, lambda: self._launch(state))

    def show_alert(self, state: BatteryState,
                   level: str, title: str, body: str) -> None:
        """Show alert version: centred, no snake, pulsing warning ring."""
        self._root.after(0, lambda: self._launch_alert(state, level, title, body))

    def preview_show(self, state: BatteryState,
                     snake_speed=None, line_width_pct=None) -> None:
        """Called from settings preview — same as show() with optional overrides."""
        self._root.after(0, lambda: self._launch(
            state,
            snake_speed_override=snake_speed,
            lw_pct_override=line_width_pct,
        ))

    def hide(self) -> None:
        self._root.after(0, self._kill)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _launch_alert(self, state: BatteryState,
                      level: str, title: str, body: str) -> None:
        self._kill()
        ahud_cfg = self._config.data.get("alert_hud", {}) if self._config else {}
        col = charge_color(state.percent)
        cfg = {
            "x":            0,   # overridden by _on_mapped using alert_pos_h/v
            "y":            0,
            "alert_pos_h":  ahud_cfg.get("pos_h", 50),
            "alert_pos_v":  ahud_cfg.get("pos_v", 50),
            "percent":      state.percent,
            "is_charging":  state.is_charging,
            "title":        state.HUD_title,
            "subtitle":     state.HUD_subtitle,
            "alert":        True,
            "alert_level":  level,
            "alert_title":  title,
            "alert_subtitle": body,
            "cr":           col[0],
            "cg":           col[1],
            "cb":           col[2],
            "anim":         "fade",
            "anim_speed":   1.5,
            "pos_v":        50,
            "win_alpha":    0.95,
            "bg":           20,
            "snake_speed":  600,
            "lw_pct":       120,
        }
        try:
            self._proc = subprocess.Popen(
                [sys.executable, _WORKER, json.dumps(cfg)],
                env=_clean_env(),
            )
        except Exception as e:
            import logging
            logging.getLogger("watt").error(f"HUD alert launch failed: {e}")

    def _kill(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None

    def _launch(self, state: BatteryState,
                snake_speed_override=None,
                lw_pct_override=None):
        self._kill()

        hud_cfg  = self._config.data.get("hud",       {}) if self._config else {}
        glow_cfg = self._config.data.get("glow",      {}) if self._config else {}
        ahud_cfg = self._config.data.get("alert_hud", {}) if self._config else {}

        x, y   = self._calc_pos()
        col    = charge_color(state.percent)
        cr_, cg, cb = col

        cfg = {
            "x":          x,
            "y":          y,
            "percent":    state.percent,
            "is_charging":state.is_charging,
            "title":      state.HUD_title,
            "subtitle":   state.HUD_subtitle,
            "cr":         cr_,
            "cg":         cg,
            "cb":         cb,
            "anim":       hud_cfg.get("animation", "bounce"),
            "anim_speed": hud_cfg.get("anim_speed", 1.0),
            "pos_v":      hud_cfg.get("position_v", 5),
            "win_alpha":  hud_cfg.get("win_alpha", 88) / 100,
            "bg":         hud_cfg.get("bg_lightness", 20),
            "snake_speed":snake_speed_override or glow_cfg.get("snake_speed", 600),
            "lw_pct":     lw_pct_override      or glow_cfg.get("line_width_pct", 120),
        }

        try:
            self._proc = subprocess.Popen(
                [sys.executable, _WORKER, json.dumps(cfg)],
                env=_clean_env(),
            )
        except Exception as e:
            import logging
            logging.getLogger("watt").error(f"HUD launch failed: {e}")

    def _calc_pos(self) -> tuple[int, int]:
        cfg   = self._config.data.get("hud", {}) if self._config else {}
        pos_v = cfg.get("position_v", 5)
        sw    = self._root.winfo_screenwidth()
        sh    = self._root.winfo_screenheight()
        mt, mb = 60, 60
        cw, ch = 344, 76
        x = (sw - cw) // 2          # always centered horizontally
        y = mt + int((sh - ch - mt - mb) * pos_v / 100)
        return x, y


# ── BatteryState display properties ────────────────────────────────────────────

def hud_title(state: BatteryState) -> str:
    if not state.has_battery: return t("hud.no_battery")
    if state.is_full:         return t("hud.fully_charged")
    if state.is_charging:     return t("hud.charging", pct=state.percent)
    return t("hud.remaining", pct=state.percent)


def hud_subtitle(state: BatteryState) -> str:
    if not state.has_battery:                        return t("hud.sub.no_battery")
    if state.is_full:                                return t("hud.sub.full")
    if not state.is_charging and state.percent <= 5: return t("hud.sub.critical")
    if state.seconds_remaining is None:              return t("hud.sub.calculating")
    label = t("hud.sub.until_full") if state.is_charging else t("hud.sub.until_empty")
    return f"{state.time_remaining_text} {label}"


BatteryState.HUD_title    = property(hud_title)
BatteryState.HUD_subtitle = property(hud_subtitle)
