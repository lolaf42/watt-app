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
import i18n
from i18n import t
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
i18n.set_lang(_config.data.get("language", "en"))
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


APP_VERSION = "v1.2.0"

# ── Battery popup window ───────────────────────────────────────────────────────

class BatteryPopup(tk.Toplevel):
    W    = 320
    BGD  = "#0B1015"
    BGC  = "#111820"
    BGC2 = "#182030"
    FGW  = "#FFFFFF"
    DIM  = "#5A6475"
    GRN  = "#3CC050"
    YLW  = "#D4A017"
    BLU  = "#4A90E2"
    RED  = "#CC2222"
    SEP  = "#1A2535"

    def __init__(self, parent: tk.Tk, state: BatteryState, click_x: int = 0, click_y: int = 0):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=self.BGD)
        self.attributes("-alpha", 0.96)
        self._build(state)
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        # Position near the tray icon (click position)
        x = max(0, min(click_x - w // 2, sw - w - 8))
        y = click_y - h - 8 if click_y > sh // 2 else click_y + 8
        y = max(0, min(y, sh - h - 8))
        self.geometry(f"+{x}+{y}")
        self.bind("<FocusOut>", lambda _e: self.destroy())
        self.focus_force()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _div(self, pady=0):
        tk.Frame(self, bg=self.SEP, height=1).pack(fill="x", pady=pady)

    def _bar(self, parent, pct, color, w=None, h=4):
        import base64, io
        from PIL import Image as PI, ImageDraw as PD
        bw = (w or self.W - 40)
        bg = tuple(int(self.SEP[i:i+2], 16) for i in (1, 3, 5))
        fc = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        img = PI.new("RGB", (bw, h), bg)
        fill = max(0, int(bw * min(pct, 100) / 100))
        if fill > 0:
            PD.Draw(img).rounded_rectangle([0, 0, fill-1, h-1], radius=2, fill=fc)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        ph = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        lbl = tk.Label(parent, image=ph, bg=parent["bg"], borderwidth=0)
        lbl.image = ph
        lbl.pack(anchor="w", pady=(4, 0))

    def _card(self, icon, icon_col, title) -> tk.Frame:
        outer = tk.Frame(self, bg=self.BGC)
        outer.pack(fill="x", padx=10, pady=3)
        hdr = tk.Frame(outer, bg=self.BGC)
        hdr.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(hdr, text=icon, bg=self.BGC, fg=icon_col,
                 font=("Segoe UI", 11)).pack(side="left")
        tk.Label(hdr, text=f"  {title}", bg=self.BGC, fg=self.FGW,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(hdr, text="ⓘ", bg=self.BGC, fg=self.DIM,
                 font=("Segoe UI", 9)).pack(side="right")
        body = tk.Frame(outer, bg=self.BGC)
        body.pack(fill="x", padx=12, pady=(0, 10))
        return body

    def _kv(self, parent, key, val, vc=None):
        f = tk.Frame(parent, bg=parent["bg"])
        f.pack(fill="x", pady=2)
        tk.Label(f, text=key, bg=parent["bg"], fg=self.DIM,
                 font=("Segoe UI", 9), anchor="w").pack(side="left")
        tk.Label(f, text=val, bg=parent["bg"], fg=vc or self.FGW,
                 font=("Segoe UI", 10, "bold"), anchor="e").pack(side="right")

    def _kv2(self, parent, k1, v1, c1, k2, v2, c2, sub2=""):
        f = tk.Frame(parent, bg=parent["bg"])
        f.pack(fill="x", pady=3)
        lf = tk.Frame(f, bg=parent["bg"])
        lf.pack(side="left", expand=True, fill="x")
        rf = tk.Frame(f, bg=parent["bg"])
        rf.pack(side="right", expand=True, fill="x")
        tk.Label(lf, text=k1, bg=parent["bg"], fg=self.DIM,
                 font=("Segoe UI", 8), anchor="w").pack(anchor="w")
        tk.Label(lf, text=v1, bg=parent["bg"], fg=c1,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(rf, text=k2, bg=parent["bg"], fg=c2,
                 font=("Segoe UI", 9, "bold"), anchor="e").pack(anchor="e")
        tk.Label(rf, text=v2, bg=parent["bg"], fg=self.DIM,
                 font=("Segoe UI", 8), anchor="e").pack(anchor="e")

    @staticmethod
    def _mah(mwh, voltage_mv):
        if voltage_mv and voltage_mv > 0:
            return f"{int(mwh * 1000 / voltage_mv):,} mAh"
        return f"{mwh / 1000:.3f} Wh"

    def _footer_btn(self, text, cmd, col, arrow=True, sub=""):
        tk.Frame(self, bg=self.SEP, height=1).pack(fill="x")
        f = tk.Frame(self, bg=self.BGD, cursor="hand2")
        f.pack(fill="x")
        f.bind("<Button-1>", lambda _: cmd())
        f.bind("<Enter>", lambda _: f.configure(bg=self.BGC2))
        f.bind("<Leave>", lambda _: f.configure(bg=self.BGD))
        inner = tk.Frame(f, bg=self.BGD)
        inner.pack(fill="x", padx=14, pady=7)
        tk.Label(inner, text=text, bg=self.BGD, fg=col,
                 font=("Segoe UI", 10), anchor="w").pack(side="left")
        if arrow:
            tk.Label(inner, text=">", bg=self.BGD, fg=self.DIM,
                     font=("Segoe UI", 10)).pack(side="right")
        elif sub:
            tk.Label(inner, text=sub, bg=self.BGD, fg=self.DIM,
                     font=("Segoe UI", 9)).pack(side="right")
        # propagate hover to children
        for w in inner.winfo_children():
            w.bind("<Button-1>", lambda _, c=cmd: c())
            w.bind("<Enter>", lambda _, ff=f: ff.configure(bg=self.BGC2))
            w.bind("<Leave>", lambda _, ff=f: ff.configure(bg=self.BGD))

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, s: BatteryState) -> None:
        import base64, io
        from PIL import Image as PI, ImageDraw as PD

        accent = (self.GRN if (s.is_charging or s.is_full)
                  else self.RED if s.percent <= 20
                  else "#FFA000" if s.percent <= 50
                  else self.GRN)
        ac_rgb = tuple(int(accent[i:i+2], 16) for i in (1, 3, 5))

        # ── Header ────────────────────────────────────────────────────────────
        hf = tk.Frame(self, bg=self.BGD)
        hf.pack(fill="x", padx=16, pady=(16, 4))

        nr = tk.Frame(hf, bg=self.BGD)
        nr.pack(anchor="w")
        tk.Label(nr, text=f"{s.percent}" if s.has_battery else "—",
                 bg=self.BGD, fg=accent,
                 font=("Segoe UI", 48, "bold")).pack(side="left")
        tk.Label(nr, text=" %", bg=self.BGD, fg=accent,
                 font=("Segoe UI", 22)).pack(side="left", anchor="s", pady=16)

        icon = "⚡" if s.is_charging else ("🪫" if s.percent <= 10 else "🔋")
        status_str = (t("status.charging") if s.is_charging else
                      t("status.full") if s.is_full else t("status.discharging"))
        sr = tk.Frame(hf, bg=self.BGD)
        sr.pack(anchor="w")
        tk.Label(sr, text=f"{icon}  {status_str}", bg=self.BGD, fg=accent,
                 font=("Segoe UI", 13)).pack(side="left")
        if s.has_battery and s.seconds_remaining is not None:
            suf = t("popup.until_full") if s.is_charging else t("popup.remaining_lbl")
            tk.Label(hf, text=f"{s.time_remaining_text} {suf}",
                     bg=self.BGD, fg=self.DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        # Progress bar
        bw = self.W - 32
        bi = PI.new("RGB", (bw, 6), tuple(int(self.SEP[i:i+2], 16) for i in (1, 3, 5)))
        if s.has_battery and s.percent > 0:
            PD.Draw(bi).rounded_rectangle(
                [0, 0, int(bw * s.percent / 100) - 1, 5], radius=3, fill=ac_rgb)
        buf = io.BytesIO(); bi.save(buf, format="PNG")
        ph = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        bar = tk.Label(self, image=ph, bg=self.BGD, borderwidth=0)
        bar.image = ph
        bar.pack(padx=16, pady=(8, 12))

        # ── Battery Information divider ───────────────────────────────────────
        self._div()
        inf_f = tk.Frame(self, bg=self.BGD)
        inf_f.pack(fill="x", padx=12, pady=(6, 4))
        tk.Label(inf_f, text="●", bg=self.BGD, fg=self.BLU,
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Label(inf_f, text="  Battery Information", bg=self.BGD, fg=self.DIM,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Label(inf_f, text="∧", bg=self.BGD, fg=self.DIM,
                 font=("Segoe UI", 9)).pack(side="right")
        self._div()

        # ── Battery Health ────────────────────────────────────────────────────
        if s.health_percent is not None:
            hc  = self.YLW if s.health_percent < 80 else self.GRN
            ico = "⚠" if s.health_percent < 80 else "✓"
            body = self._card(ico, hc, t("popup.health"))

            hr = tk.Frame(body, bg=self.BGC)
            hr.pack(fill="x")
            lf = tk.Frame(hr, bg=self.BGC)
            lf.pack(side="left")
            tk.Label(lf, text=f"{s.health_percent:.0f}%",
                     bg=self.BGC, fg=hc,
                     font=("Segoe UI", 24, "bold")).pack(side="left")
            tk.Label(lf, text=f"  {s.health_label}",
                     bg=self.BGC, fg=hc,
                     font=("Segoe UI", 12)).pack(side="left", anchor="s", pady=6)

            if s.cycle_count is not None:
                rf2 = tk.Frame(hr, bg=self.BGC)
                rf2.pack(side="right", anchor="ne")
                tk.Label(rf2, text=f"{s.cycle_count:,}",
                         bg=self.BGC, fg=self.FGW,
                         font=("Segoe UI", 13, "bold"), anchor="e").pack(anchor="e")
                tk.Label(rf2, text=t("popup.cycle"), bg=self.BGC, fg=self.DIM,
                         font=("Segoe UI", 8), anchor="e").pack(anchor="e")

            self._bar(body, s.health_percent, hc, w=self.W-40)

            if s.health_percent < 80:
                tk.Frame(body, bg=self.SEP, height=1).pack(fill="x", pady=(6, 4))
                tk.Label(body, text=t("popup.service"), bg=self.BGC, fg=self.DIM,
                         font=("Segoe UI", 8), wraplength=self.W-50,
                         anchor="w").pack(anchor="w")

        # ── Temperature ───────────────────────────────────────────────────────
        if s.temperature_celsius is not None:
            tc = (self.RED if s.temperature_celsius >= 50
                  else "#FFA000" if s.temperature_celsius >= 40 else self.GRN)
            body = self._card("✓", tc, t("popup.temp"))
            tr = tk.Frame(body, bg=self.BGC)
            tr.pack(fill="x")
            lf = tk.Frame(tr, bg=self.BGC)
            lf.pack(side="left")
            tk.Label(lf, text=f"🌡 {s.temperature_celsius:.1f}°C",
                     bg=self.BGC, fg=tc, font=("Segoe UI", 18, "bold")).pack(anchor="w")
            tk.Label(lf, text=f"   {s.temperature_celsius*9/5+32:.1f}°F",
                     bg=self.BGC, fg=self.DIM, font=("Segoe UI", 10)).pack(anchor="w")
            rf2 = tk.Frame(tr, bg=self.BGC)
            rf2.pack(side="right", anchor="ne")
            sc = self.GRN if s.temperature_celsius < 40 else "#FFA000"
            label_n = "● Normal" if s.temperature_celsius < 40 else "● High"
            tk.Label(rf2, text=label_n, bg=self.BGC, fg=sc,
                     font=("Segoe UI", 10, "bold"), anchor="e").pack(anchor="e")
            tk.Label(rf2,
                     text=t("popup.optimal") if s.temperature_celsius < 40 else t("popup.high_temp"),
                     bg=self.BGC, fg=self.DIM, font=("Segoe UI", 8), anchor="e").pack(anchor="e")

        # ── Power & Electrical ────────────────────────────────────────────────
        if s.voltage_mv is not None or s.power_watts is not None:
            body = self._card("⚡", self.GRN, t("popup.power"))
            f = tk.Frame(body, bg=self.BGC)
            f.pack(fill="x", pady=2)
            lf = tk.Frame(f, bg=self.BGC)
            lf.pack(side="left", expand=True, fill="x")
            rf2 = tk.Frame(f, bg=self.BGC)
            rf2.pack(side="right", expand=True, fill="x")
            tk.Label(lf, text=t("popup.power_usage"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="w").pack(anchor="w")
            tk.Label(lf,
                     text=f"{s.power_watts:.1f} W" if s.power_watts is not None else "N/A",
                     bg=self.BGC, fg=self.FGW,
                     font=("Segoe UI", 16, "bold")).pack(anchor="w")
            tk.Label(rf2, text=t("popup.voltage"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="e").pack(anchor="e")
            tk.Label(rf2,
                     text=f"{s.voltage_mv/1000:.2f} V" if s.voltage_mv else "N/A",
                     bg=self.BGC, fg=self.FGW,
                     font=("Segoe UI", 16, "bold"), anchor="e").pack(anchor="e")

            f2 = tk.Frame(body, bg=self.BGC)
            f2.pack(fill="x", pady=2)
            lf2 = tk.Frame(f2, bg=self.BGC)
            lf2.pack(side="left", expand=True, fill="x")
            rf3 = tk.Frame(f2, bg=self.BGC)
            rf3.pack(side="right", expand=True, fill="x")
            cc = self.GRN if s.is_charging else self.DIM
            chg_txt = (f"⚡ {t('popup.charging')}" if s.is_charging
                       else t("popup.discharging"))
            tk.Label(lf2, text=t("popup.current"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="w").pack(anchor="w")
            cur_row = tk.Frame(lf2, bg=self.BGC)
            cur_row.pack(anchor="w")
            tk.Label(cur_row,
                     text=f"{s.current_ma:,} mA" if s.current_ma else "N/A",
                     bg=self.BGC, fg=self.FGW,
                     font=("Segoe UI", 15, "bold")).pack(side="left")
            if s.is_charging:
                tk.Label(cur_row, text=" ●", bg=self.BGC, fg=self.GRN,
                         font=("Segoe UI", 8)).pack(side="left", anchor="s", pady=3)
            tk.Label(rf3, text=chg_txt, bg=self.BGC, fg=cc,
                     font=("Segoe UI", 9, "bold"), anchor="e").pack(anchor="e")
            tk.Label(rf3, text=t("popup.normal_v"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 8), anchor="e").pack(anchor="e")

        # ── Capacity Details ──────────────────────────────────────────────────
        if s.remaining_mwh is not None:
            body = self._card("══", self.BLU, t("popup.capacity"))
            self._kv(body, t("popup.remaining"),
                     self._mah(s.remaining_mwh, s.voltage_mv), self.GRN)
            if s.full_capacity_mwh:
                self._kv(body, t("popup.curr_full"),
                         self._mah(s.full_capacity_mwh, s.voltage_mv), self.BLU)
            if s.design_capacity_mwh:
                self._kv(body, t("popup.design"),
                         self._mah(s.design_capacity_mwh, s.voltage_mv), self.DIM)

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Frame(self, bg=self.SEP, height=1).pack(fill="x", pady=(8, 0))
        self._footer_btn(t("popup.settings"), _on_settings, self.FGW, arrow=True)
        self._footer_btn("🔋  Battery Settings...", lambda: None, self.DIM, arrow=True)
        self._footer_btn(t("popup.quit"), _on_quit, self.RED,
                         arrow=False, sub=APP_VERSION)


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
                _tray.title = (t("tray.title", pct=new.percent, status=new.status_text)
                               if new.has_battery else t("tray.no_battery"))

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
    mx, my = _root.winfo_pointerxy() if _root else (0, 0)
    _popup = BatteryPopup(_root, state, click_x=mx, click_y=my)


def _on_settings(_icon=None, _item=None) -> None:
    _root.after(0, _open_settings)


def _open_settings() -> None:
    global _settings_win
    if _settings_win and _settings_win.winfo_exists():
        _settings_win.lift()
        return

    def _hud_preview(speed: int, lw_pct: int, anim_speed: float) -> None:
        if not _hud: return
        _config.data.setdefault("hud", {})["anim_speed"] = anim_speed
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
    global _tray, _root, _hud, _glow, _state, _prev_state

    _state = get_battery_state()
    _prev_state = _state   # prevents first poll from re-triggering glow

    _root = tk.Tk()
    _root.withdraw()
    _root.title("Watt")

    _hud  = HudOverlay(_root, _config)
    _glow = ScreenGlow(_root, _config)

    menu = pystray.Menu(
        pystray.MenuItem(t("tray.details"), _on_details, default=True),
        pystray.MenuItem(t("tray.settings"), _on_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("tray.quit"), _on_quit),
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
