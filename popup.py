"""BatteryPopup — tray-click battery detail window with flicker-free live refresh."""

import base64
import io
import subprocess
import sys
import tkinter as tk
from typing import Callable, Optional

from PIL import Image as PI, ImageDraw as PD

from battery import BatteryState, get_battery_state
from i18n import t


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

    def __init__(self, parent: tk.Tk, state: BatteryState,
                 click_x: int = 0, click_y: int = 0,
                 on_settings: Callable = None,
                 on_quit: Callable = None,
                 app_version: str = "",
                 state_fn: Callable = None,
                 from_hover: bool = False):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=self.BGD)
        self.attributes("-alpha", 0.96)

        self._on_settings = on_settings or (lambda: None)
        self._on_quit     = on_quit     or (lambda: None)
        self._app_version = app_version
        self._state_fn    = state_fn
        self._refs: dict  = {}   # dynamic widget references

        self._body = tk.Frame(self, bg=self.BGD)
        self._body.pack(fill="x")

        self._build_body(state)
        self._build_footer()

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        x = max(0, min(click_x - w // 2, sw - w - 8))
        if click_y > sh // 2:
            y = click_y - h - 8          # below center → popup above click
        elif click_y < 80:
            y = 76                        # top panel icon → popup below panel
        else:
            y = click_y + 8
        y = max(0, min(y, sh - h - 8))
        self.geometry(f"+{x}+{y}")
        if not from_hover:
            self.focus_force()
            self.grab_set()
        self.after(400, self._arm_close)

        if self._state_fn:
            self.after(1000, self._tick)

    # ── Live refresh (no flicker — only .config() on existing widgets) ─────────

    def _tick(self):
        if not self.winfo_exists():
            return
        try:
            self._update_values(self._state_fn())
        except Exception:
            pass
        self.after(1000, self._tick)

    def _update_values(self, s: BatteryState) -> None:
        r  = self._refs
        ac = (self.GRN if (s.is_charging or s.is_full)
              else self.RED if s.percent <= 20
              else "#FFA000" if s.percent <= 50
              else self.GRN)

        # Header
        if "pct"    in r: r["pct"].config(text=str(s.percent) if s.has_battery else "—", fg=ac)
        if "pct_s"  in r: r["pct_s"].config(fg=ac)
        icon = "⚡" if s.is_charging else ("🪫" if s.percent <= 10 else "🔋")
        st   = (t("status.charging") if s.is_charging else
                t("status.full") if s.is_full else t("status.discharging"))
        if "stat"   in r: r["stat"].config(text=f"{icon}  {st}", fg=ac)
        if "time"   in r:
            if s.seconds_remaining is not None:
                suf = t("popup.until_full") if s.is_charging else t("popup.remaining_lbl")
                r["time"].config(text=f"{s.time_remaining_text} {suf}")
            else:
                r["time"].config(text="")

        # Progress bar (regenerate image, swap reference)
        if "bar" in r:
            ac_rgb = tuple(int(ac[i:i+2], 16) for i in (1, 3, 5))
            bw = self.W - 32
            bg = tuple(int(self.SEP[i:i+2], 16) for i in (1, 3, 5))
            bi = PI.new("RGB", (bw, 6), bg)
            if s.has_battery and s.percent > 0:
                PD.Draw(bi).rounded_rectangle(
                    [0, 0, int(bw * s.percent / 100) - 1, 5], radius=3, fill=ac_rgb)
            buf = io.BytesIO(); bi.save(buf, format="PNG")
            ph = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
            r["bar"].config(image=ph)
            r["bar"].image = ph

        # Temperature
        if s.temperature_celsius is not None:
            tc = (self.RED if s.temperature_celsius >= 50
                  else "#FFA000" if s.temperature_celsius >= 40 else self.GRN)
            if "temp"      in r: r["temp"].config(text=f"🌡 {s.temperature_celsius:.0f}°C", fg=tc)
            if "temp_f"    in r: r["temp_f"].config(text=f"   {s.temperature_celsius*9/5+32:.0f}°F")
            sc = self.GRN if s.temperature_celsius < 40 else "#FFA000"
            ln = "● Normal" if s.temperature_celsius < 40 else "● High"
            if "temp_st"   in r: r["temp_st"].config(text=ln, fg=sc)
            ti = t("popup.optimal") if s.temperature_celsius < 40 else t("popup.high_temp")
            if "temp_info" in r: r["temp_info"].config(text=ti)

        # Power & Electrical
        arrow     = "▲" if s.is_charging else "▼"
        arrow_col = self.GRN if s.is_charging else self.RED
        dir_lbl   = t("popup.charging") if s.is_charging else t("popup.discharging")
        if "power"     in r:
            r["power"].config(text=f"{s.power_watts:.1f} W" if s.power_watts is not None else "N/A")
        if "arrow_pw"  in r: r["arrow_pw"].config(text=f" {arrow}", fg=arrow_col)
        if "voltage"   in r:
            r["voltage"].config(text=f"{s.voltage_mv/1000:.2f} V" if s.voltage_mv else "N/A")
        if "current"   in r:
            r["current"].config(text=f"{s.current_ma:,} mA" if s.current_ma else "N/A")
        if "arrow_cur" in r: r["arrow_cur"].config(text=f" {arrow}", fg=arrow_col)
        if "dir"       in r: r["dir"].config(text=f"{arrow} {dir_lbl}", fg=arrow_col)

        # Capacity
        if "remain" in r and s.remaining_mwh is not None:
            r["remain"].config(text=self._mah(s.remaining_mwh, s.voltage_mv))

    # ── Close logic ───────────────────────────────────────────────────────────

    def _arm_close(self):
        if not self.winfo_exists():
            return
        self.bind("<ButtonPress>", self._on_press)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Leave>", self._on_mouse_leave)

    def _on_press(self, event):
        """Close if the click landed outside the popup (uses screen coords)."""
        if not self.winfo_exists():
            return
        try:
            px, py = self.winfo_x(), self.winfo_y()
            pw, ph = self.winfo_width(), self.winfo_height()
            if not (px <= event.x_root <= px + pw and
                    py <= event.y_root <= py + ph):
                self.destroy()
        except Exception:
            self.destroy()

    def _on_mouse_leave(self, event):
        if event.widget is self:
            self.after(600, self._close_if_outside)

    def _close_if_outside(self):
        if not self.winfo_exists():
            return
        try:
            mx = self.winfo_pointerx()
            my = self.winfo_pointery()
            wx, wy = self.winfo_x(), self.winfo_y()
            ww, wh = self.winfo_width(), self.winfo_height()
            in_popup = wx - 8 <= mx <= wx + ww + 8 and wy - 8 <= my <= wy + wh + 8
            in_panel = my < 72   # mouse is back over tray icon — don't close
            if not in_popup and not in_panel:
                self.destroy()
        except Exception:
            self.destroy()

    def _on_focus_out(self, event):
        """Close when the popup loses focus to another application."""
        if event.widget is self:
            self.after(80, self._close_if_unfocused)

    def _close_if_unfocused(self):
        if not self.winfo_exists():
            return
        try:
            if self.focus_get() is None:
                self.destroy()
        except Exception:
            self.destroy()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _div(self, pady=0):
        tk.Frame(self._body, bg=self.SEP, height=1).pack(fill="x", pady=pady)

    def _bar(self, parent, pct, color, w=None, h=4):
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
        outer = tk.Frame(self._body, bg=self.BGC)
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

    def _kv(self, parent, key, val, vc=None, ref_key: str = None):
        f = tk.Frame(parent, bg=parent["bg"])
        f.pack(fill="x", pady=2)
        tk.Label(f, text=key, bg=parent["bg"], fg=self.DIM,
                 font=("Segoe UI", 9), anchor="w").pack(side="left")
        lbl = tk.Label(f, text=val, bg=parent["bg"], fg=vc or self.FGW,
                       font=("Segoe UI", 10, "bold"), anchor="e")
        lbl.pack(side="right")
        if ref_key:
            self._refs[ref_key] = lbl

    @staticmethod
    def _mah(mwh, voltage_mv):
        if voltage_mv and voltage_mv > 0:
            return f"{int(mwh * 1000 / voltage_mv):,} mAh"
        return f"{mwh / 1000:.3f} Wh"

    # ── Body (built once, values updated via _update_values) ─────────────────

    def _build_body(self, s: BatteryState) -> None:
        r = self._refs
        accent = (self.GRN if (s.is_charging or s.is_full)
                  else self.RED if s.percent <= 20
                  else "#FFA000" if s.percent <= 50
                  else self.GRN)
        ac_rgb = tuple(int(accent[i:i+2], 16) for i in (1, 3, 5))

        # ── Header ───────────────────────────────────────────────────────────
        hf = tk.Frame(self._body, bg=self.BGD)
        hf.pack(fill="x", padx=16, pady=(16, 4))

        nr = tk.Frame(hf, bg=self.BGD)
        nr.pack(anchor="w")
        r["pct"] = tk.Label(nr, text=f"{s.percent}" if s.has_battery else "—",
                            bg=self.BGD, fg=accent, font=("Segoe UI", 48, "bold"))
        r["pct"].pack(side="left")
        r["pct_s"] = tk.Label(nr, text=" %", bg=self.BGD, fg=accent, font=("Segoe UI", 22))
        r["pct_s"].pack(side="left", anchor="s", pady=16)

        icon = "⚡" if s.is_charging else ("🪫" if s.percent <= 10 else "🔋")
        st   = (t("status.charging") if s.is_charging else
                t("status.full") if s.is_full else t("status.discharging"))
        sr = tk.Frame(hf, bg=self.BGD)
        sr.pack(anchor="w")
        r["stat"] = tk.Label(sr, text=f"{icon}  {st}", bg=self.BGD, fg=accent,
                             font=("Segoe UI", 13))
        r["stat"].pack(side="left")

        suf = t("popup.until_full") if s.is_charging else t("popup.remaining_lbl")
        time_txt = (f"{s.time_remaining_text} {suf}"
                    if s.has_battery and s.seconds_remaining is not None else "")
        r["time"] = tk.Label(hf, text=time_txt, bg=self.BGD, fg=self.DIM,
                             font=("Segoe UI", 9))
        r["time"].pack(anchor="w", pady=(2, 0))

        # Progress bar
        bw = self.W - 32
        bi = PI.new("RGB", (bw, 6), tuple(int(self.SEP[i:i+2], 16) for i in (1, 3, 5)))
        if s.has_battery and s.percent > 0:
            PD.Draw(bi).rounded_rectangle(
                [0, 0, int(bw * s.percent / 100) - 1, 5], radius=3, fill=ac_rgb)
        buf = io.BytesIO(); bi.save(buf, format="PNG")
        ph = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        r["bar"] = tk.Label(self._body, image=ph, bg=self.BGD, borderwidth=0)
        r["bar"].image = ph
        r["bar"].pack(padx=16, pady=(8, 12))

        # ── Battery Information divider ───────────────────────────────────────
        self._div()
        inf_f = tk.Frame(self._body, bg=self.BGD)
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
            hr = tk.Frame(body, bg=self.BGC); hr.pack(fill="x")
            lf = tk.Frame(hr, bg=self.BGC); lf.pack(side="left")
            tk.Label(lf, text=f"{s.health_percent:.0f}%", bg=self.BGC, fg=hc,
                     font=("Segoe UI", 24, "bold")).pack(side="left")
            tk.Label(lf, text=f"  {s.health_label}", bg=self.BGC, fg=hc,
                     font=("Segoe UI", 12)).pack(side="left", anchor="s", pady=6)
            if s.cycle_count is not None:
                rf2 = tk.Frame(hr, bg=self.BGC); rf2.pack(side="right", anchor="ne")
                tk.Label(rf2, text=f"{s.cycle_count:,}", bg=self.BGC, fg=self.FGW,
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
            temp_title = (t("popup.temp") if s.temperature_is_battery
                          else "Board Temp")
            body = self._card("✓", tc, temp_title)
            tr = tk.Frame(body, bg=self.BGC); tr.pack(fill="x")
            lf = tk.Frame(tr, bg=self.BGC); lf.pack(side="left")
            r["temp"] = tk.Label(lf, text=f"🌡 {s.temperature_celsius:.0f}°C",
                                 bg=self.BGC, fg=tc, font=("Segoe UI", 18, "bold"))
            r["temp"].pack(anchor="w")
            r["temp_f"] = tk.Label(lf, text=f"   {s.temperature_celsius*9/5+32:.0f}°F",
                                   bg=self.BGC, fg=self.DIM, font=("Segoe UI", 10))
            r["temp_f"].pack(anchor="w")
            rf2 = tk.Frame(tr, bg=self.BGC); rf2.pack(side="right", anchor="ne")
            sc = self.GRN if s.temperature_celsius < 40 else "#FFA000"
            ln = "● Normal" if s.temperature_celsius < 40 else "● High"
            r["temp_st"] = tk.Label(rf2, text=ln, bg=self.BGC, fg=sc,
                                    font=("Segoe UI", 10, "bold"), anchor="e")
            r["temp_st"].pack(anchor="e")
            ti = t("popup.optimal") if s.temperature_celsius < 40 else t("popup.high_temp")
            r["temp_info"] = tk.Label(rf2, text=ti, bg=self.BGC, fg=self.DIM,
                                      font=("Segoe UI", 8), anchor="e")
            r["temp_info"].pack(anchor="e")

        # ── Power & Electrical ────────────────────────────────────────────────
        if s.voltage_mv is not None or s.power_watts is not None:
            arrow     = "▲" if s.is_charging else "▼"
            arrow_col = self.GRN if s.is_charging else self.RED
            dir_lbl   = t("popup.charging") if s.is_charging else t("popup.discharging")

            body = self._card("⚡", self.GRN, t("popup.power"))
            r1 = tk.Frame(body, bg=self.BGC); r1.pack(fill="x", pady=2)
            lf = tk.Frame(r1, bg=self.BGC); lf.pack(side="left", expand=True, fill="x")
            rf2 = tk.Frame(r1, bg=self.BGC); rf2.pack(side="right", expand=True, fill="x")

            tk.Label(lf, text=t("popup.power_usage"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="w").pack(anchor="w")
            pw_row = tk.Frame(lf, bg=self.BGC); pw_row.pack(anchor="w")
            r["power"] = tk.Label(pw_row,
                                  text=f"{s.power_watts:.1f} W" if s.power_watts is not None else "N/A",
                                  bg=self.BGC, fg=self.FGW, font=("Segoe UI", 16, "bold"))
            r["power"].pack(side="left")
            r["arrow_pw"] = tk.Label(pw_row, text=f" {arrow}", bg=self.BGC, fg=arrow_col,
                                     font=("Segoe UI", 13, "bold"))
            r["arrow_pw"].pack(side="left", anchor="s", pady=2)

            tk.Label(rf2, text=t("popup.voltage"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="e").pack(anchor="e")
            r["voltage"] = tk.Label(rf2,
                                    text=f"{s.voltage_mv/1000:.2f} V" if s.voltage_mv else "N/A",
                                    bg=self.BGC, fg=self.FGW,
                                    font=("Segoe UI", 16, "bold"), anchor="e")
            r["voltage"].pack(anchor="e")

            r2 = tk.Frame(body, bg=self.BGC); r2.pack(fill="x", pady=2)
            lf2 = tk.Frame(r2, bg=self.BGC); lf2.pack(side="left", expand=True, fill="x")
            rf3 = tk.Frame(r2, bg=self.BGC); rf3.pack(side="right", expand=True, fill="x")

            tk.Label(lf2, text=t("popup.current"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 9), anchor="w").pack(anchor="w")
            cur_row = tk.Frame(lf2, bg=self.BGC); cur_row.pack(anchor="w")
            r["current"] = tk.Label(cur_row,
                                    text=f"{s.current_ma:,} mA" if s.current_ma else "N/A",
                                    bg=self.BGC, fg=self.FGW, font=("Segoe UI", 15, "bold"))
            r["current"].pack(side="left")
            r["arrow_cur"] = tk.Label(cur_row, text=f" {arrow}", bg=self.BGC, fg=arrow_col,
                                      font=("Segoe UI", 11, "bold"))
            r["arrow_cur"].pack(side="left", anchor="s", pady=3)

            r["dir"] = tk.Label(rf3, text=f"{arrow} {dir_lbl}", bg=self.BGC, fg=arrow_col,
                                font=("Segoe UI", 9, "bold"), anchor="e")
            r["dir"].pack(anchor="e")
            tk.Label(rf3, text=t("popup.normal_v"), bg=self.BGC, fg=self.DIM,
                     font=("Segoe UI", 8), anchor="e").pack(anchor="e")

        # ── Capacity Details ──────────────────────────────────────────────────
        if s.remaining_mwh is not None:
            body = self._card("══", self.BLU, t("popup.capacity"))
            self._kv(body, t("popup.remaining"),
                     self._mah(s.remaining_mwh, s.voltage_mv), self.GRN, ref_key="remain")
            if s.full_capacity_mwh:
                self._kv(body, t("popup.curr_full"),
                         self._mah(s.full_capacity_mwh, s.voltage_mv), self.BLU)
            if s.design_capacity_mwh:
                self._kv(body, t("popup.design"),
                         self._mah(s.design_capacity_mwh, s.voltage_mv), self.DIM)

    # ── Footer (static) ───────────────────────────────────────────────────────

    def _build_footer(self):
        tk.Frame(self, bg=self.SEP, height=1).pack(fill="x", pady=(8, 0))
        self._footer_btn(t("popup.settings"), self._on_settings, self.FGW, arrow=True)
        self._footer_btn("🔋  Battery Settings...", _open_power_settings, self.DIM, arrow=True)
        self._footer_btn(t("popup.quit"), self._on_quit, self.RED,
                         arrow=False, sub=self._app_version)

    def _footer_btn(self, text, cmd, col, arrow=True, sub=""):
        def _invoke(_event=None):
            self.destroy()
            cmd()

        tk.Frame(self, bg=self.SEP, height=1).pack(fill="x")
        f = tk.Frame(self, bg=self.BGD, cursor="hand2")
        f.pack(fill="x")
        f.bind("<Button-1>", _invoke)
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
        for w in inner.winfo_children():
            w.bind("<Button-1>", _invoke)
            w.bind("<Enter>", lambda _, ff=f: ff.configure(bg=self.BGC2))
            w.bind("<Leave>", lambda _, ff=f: ff.configure(bg=self.BGD))


def _open_power_settings() -> None:
    cmds = (
        [["gnome-control-center", "power"]]
        if sys.platform != "win32" else
        [["powercfg.cpl"]]
    )
    cmds += [["xdg-open", "x-scheme-handler/settings"]]
    for cmd in cmds:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    state = get_battery_state()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    # Simulate tray icon at top-right of screen (GNOME top panel)
    popup = BatteryPopup(
        root, state,
        click_x=sw - 40,
        click_y=30,
        on_settings=lambda: print("Settings clicked"),
        on_quit=root.quit,
        app_version="v1.4.0 — Demo",
        state_fn=get_battery_state,
    )
    root.mainloop()
