"""BatteryPopup — tray-click battery detail window."""

import base64
import io
import tkinter as tk
from typing import Callable

from PIL import Image as PI, ImageDraw as PD

from battery import BatteryState
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
                 app_version: str = ""):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=self.BGD)
        self.attributes("-alpha", 0.96)

        self._on_settings  = on_settings  or (lambda: None)
        self._on_quit      = on_quit      or (lambda: None)
        self._app_version  = app_version

        self._build(state)
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        x = max(0, min(click_x - w // 2, sw - w - 8))
        y = click_y - h - 8 if click_y > sh // 2 else click_y + 8
        y = max(0, min(y, sh - h - 8))
        self.geometry(f"+{x}+{y}")
        self.focus_force()
        self.grab_set()
        self.after(300, self._arm_close)

    def _arm_close(self):
        if self.winfo_exists():
            self.bind("<Button-1>", self._on_click)

    def _on_click(self, event):
        if not (0 <= event.x <= self.winfo_width() and
                0 <= event.y <= self.winfo_height()):
            self.destroy()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _div(self, pady=0):
        tk.Frame(self, bg=self.SEP, height=1).pack(fill="x", pady=pady)

    def _bar(self, parent, pct, color, w=None, h=4):
        bw = (w or self.W - 40)
        bg = tuple(int(self.SEP[i:i+2], 16) for i in (1, 3, 5))
        fc = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        img = PI.new("RGB", (bw, h), bg)
        fill = max(0, int(bw * min(pct, 100) / 100))
        if fill > 0:
            PD.Draw(img).rounded_rectangle([0, 0, fill-1, h-1], radius=2, fill=fc)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
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

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self, s: BatteryState) -> None:
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
                     bg=self.BGD, fg=self.DIM,
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        # Progress bar
        bw = self.W - 32
        bi = PI.new("RGB", (bw, 6), tuple(int(self.SEP[i:i+2], 16) for i in (1, 3, 5)))
        if s.has_battery and s.percent > 0:
            PD.Draw(bi).rounded_rectangle(
                [0, 0, int(bw * s.percent / 100) - 1, 5], radius=3, fill=ac_rgb)
        buf = io.BytesIO()
        bi.save(buf, format="PNG")
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
        self._footer_btn(t("popup.settings"), self._on_settings, self.FGW, arrow=True)
        self._footer_btn("🔋  Battery Settings...", lambda: None, self.DIM, arrow=True)
        self._footer_btn(t("popup.quit"), self._on_quit, self.RED,
                         arrow=False, sub=self._app_version)


if __name__ == "__main__":
    from battery import get_battery_state

    root = tk.Tk()
    root.withdraw()

    state = get_battery_state()

    popup = BatteryPopup(
        root, state,
        click_x=root.winfo_screenwidth() // 2,
        click_y=root.winfo_screenheight() // 2,
        on_settings=lambda: print("Settings clicked"),
        on_quit=root.quit,
        app_version="v1.3.0 — Demo",
    )
    root.mainloop()
