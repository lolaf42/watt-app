"""Settings window — tkinter, dark themed."""

import copy
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from config import ConfigManager
from autostart import set_autostart
from i18n import t, LANG_NAMES, get_lang, set_lang

BG = "#0D1117"
BG2 = "#161B22"
BG3 = "#21262D"
FG = "#C9D1D9"
GREEN = "#00CC00"
BTN = "#21262D"


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, config: ConfigManager,
                 on_save: Callable,
                 on_preview: Callable = None,
                 on_hud_preview: Callable = None,
                 on_pos_preview: Callable = None):
        super().__init__(parent)
        self.title(t("settings.title"))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._config          = config
        self._on_save         = on_save
        self._on_preview      = on_preview
        self._on_hud_preview  = on_hud_preview
        self._on_pos_preview  = on_pos_preview
        self._preview_job:     str | None = None
        self._hud_preview_job: str | None = None
        self._pos_preview_job: str | None = None
        self._ready           = False
        self._data = copy.deepcopy(config.data)  # snapshot for cancel

        self._build()
        self.update_idletasks()
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.after(300, lambda: setattr(self, '_ready', True))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, title: str) -> tk.Frame:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(outer, text=title, bg=BG, fg=GREEN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Frame(outer, bg=BG3, height=1).pack(fill="x", pady=(3, 0))
        return outer

    def _slider_row(self, parent, label, var, from_, to, fmt, preview="glow"):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG,
                 font=("Segoe UI", 10), width=26, anchor="w").pack(side="left")
        val_lbl = tk.Label(row, bg=BG, fg=GREEN,
                           font=("Segoe UI", 10), width=7, anchor="e")
        val_lbl.pack(side="right")
        def _upd(v, lbl=val_lbl, f=fmt):
            lbl.config(text=f.format(float(v)))
            if preview == "hud":
                self._schedule_hud_preview()
            elif preview == "pos":
                self._schedule_pos_preview()
            elif preview != "none":
                self._schedule_preview()
        sl = tk.Scale(row, variable=var, from_=from_, to=to,
                      orient="horizontal", bg=BG, fg=FG,
                      troughcolor=BG3, highlightthickness=0,
                      sliderrelief="flat", showvalue=False,
                      command=_upd, length=180)
        sl.pack(side="left", padx=6)
        val_lbl.config(text=fmt.format(float(var.get())))

    # ── Build ─────────────────────────────────────────────────────────────────

    # ── Threshold chip helpers ────────────────────────────────────────────────

    def _render_chips(self, container: tk.Frame, values: list[int],
                      remove_cb) -> None:
        for w in container.winfo_children():
            w.destroy()
        for v in sorted(values):
            chip = tk.Frame(container, bg=BG3, padx=6, pady=2)
            chip.pack(side="left", padx=(0, 4), pady=2)
            tk.Label(chip, text=f"{v}%", bg=BG3, fg=FG,
                     font=("Segoe UI", 9)).pack(side="left")
            x_btn = tk.Label(chip, text="✕", bg=BG3, fg="#666666",
                             font=("Segoe UI", 8), cursor="hand2", padx=2)
            x_btn.pack(side="left")
            x_btn.bind("<Button-1>", lambda _e, val=v: remove_cb(val))
            x_btn.bind("<Enter>", lambda _e, b=x_btn: b.config(fg="#CCCCCC"))
            x_btn.bind("<Leave>", lambda _e, b=x_btn: b.config(fg="#666666"))

    def _add_threshold(self, values: list[int], container: tk.Frame,
                       entry_var: tk.StringVar, remove_cb, add_cb,
                       value: int | None = None) -> None:
        try:
            v = int(entry_var.get()) if value is None else value
            assert 1 <= v <= 99
        except (ValueError, AssertionError):
            return
        if v not in values:
            values.append(v)
            self._render_chips(container, values, remove_cb)
        if value is None:
            entry_var.set("")

    def _remove_threshold(self, values: list[int], container: tk.Frame,
                          remove_cb, value: int) -> None:
        if value in values:
            values.remove(value)
        self._render_chips(container, values, remove_cb)

    def _thresh_section(self, parent: tk.Frame, label: str,
                        values: list[int], presets: list[int]) -> list[int]:
        """Build a threshold sub-section; returns the mutable values list."""
        tk.Label(parent, text=label, bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(6, 2))

        # Chip container
        chip_frame = tk.Frame(parent, bg=BG)
        chip_frame.pack(fill="x", anchor="w")

        entry_var = tk.StringVar()

        def remove_cb(val):
            self._remove_threshold(values, chip_frame,
                                   lambda v: remove_cb(v), val)

        def add_cb(val=None):
            self._add_threshold(values, chip_frame, entry_var,
                                lambda v: remove_cb(v),
                                lambda v=None: add_cb(v), val)

        self._render_chips(chip_frame, values, remove_cb)

        # Presets row
        preset_row = tk.Frame(parent, bg=BG)
        preset_row.pack(fill="x", pady=(4, 0))
        tk.Label(preset_row, text=t("settings.alerts_presets"), bg=BG, fg="#666666",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
        for pv in presets:
            btn = tk.Label(preset_row, text=f"{pv}%", bg=BG2, fg=FG,
                           font=("Segoe UI", 8), cursor="hand2",
                           padx=5, pady=2)
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda _e, v=pv: add_cb(v))
            btn.bind("<Enter>", lambda _e, b=btn: b.config(bg=BG3))
            btn.bind("<Leave>", lambda _e, b=btn: b.config(bg=BG2))

        # Custom entry row
        custom_row = tk.Frame(parent, bg=BG)
        custom_row.pack(fill="x", pady=(4, 0))
        tk.Label(custom_row, text=t("settings.alerts_custom"), bg=BG, fg="#666666",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
        ent = tk.Entry(custom_row, textvariable=entry_var, width=5,
                       bg=BG2, fg=FG, insertbackground=FG, relief="flat")
        ent.pack(side="left", padx=(0, 4))
        ent.bind("<Return>", lambda _e: add_cb())
        tk.Button(custom_row, text=t("settings.alerts_add"), command=add_cb,
                  bg=BTN, fg=FG, relief="flat", padx=8, pady=1,
                  cursor="hand2", font=("Segoe UI", 8)).pack(side="left")

        return values

    def _build(self):
        hc  = self._data.get("hud", {})
        gc  = self._data.get("glow", {})
        ahc = self._data.get("alert_hud", {})

        # Mutable threshold lists (separate from _data until Save)
        th = self._data.get("thresholds", {})
        self._low_thresholds  = list(th.get("low", [5, 10, 20]))
        self._high_thresholds = list(th.get("high", [80]))

        # ── HUD Window ──────────────────────────────────────────────────────
        self._section(t("settings.hud"))
        hud_f = tk.Frame(self, bg=BG)
        hud_f.pack(fill="x", padx=24, pady=4)

        self._v_pos_v = tk.IntVar(value=hc.get("position_v", 5))
        self._slider_row(hud_f, t("settings.pos_v"),
                         self._v_pos_v, 0, 100, "{:.0f} %", preview="pos")

        self._v_anim = tk.StringVar(value=hc.get("animation", "bounce"))
        anim_row = tk.Frame(hud_f, bg=BG)
        anim_row.pack(fill="x", pady=4)
        tk.Label(anim_row, text=t("settings.animation"), bg=BG, fg=FG,
                 font=("Segoe UI", 10), width=26, anchor="w").pack(side="left")
        for key, lbl_key in [("bounce","settings.bounce"),
                              ("slide","settings.slide"),
                              ("fade","settings.fade"),
                              ("none","settings.none")]:
            tk.Radiobutton(anim_row, text=t(lbl_key), variable=self._v_anim, value=key,
                           bg=BG, fg=FG, selectcolor=BG2,
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 10)).pack(side="left", padx=6)
        # trigger HUD preview when animation type changes
        self._v_anim.trace_add("write", lambda *_: self._schedule_hud_preview())

        self._v_anim_speed = tk.DoubleVar(value=hc.get("anim_speed", 1.0))
        self._slider_row(hud_f, t("settings.anim_speed"),
                         self._v_anim_speed, 0.25, 3.0, "{:.2f}×", preview="hud")

        self._v_bg_light = tk.IntVar(value=hc.get("bg_lightness", 20))
        self._slider_row(hud_f, t("settings.bg_lightness"),
                         self._v_bg_light, 0, 80, "{:.0f}", preview="hud")

        self._v_win_alpha = tk.IntVar(value=hc.get("win_alpha", 88))
        self._slider_row(hud_f, t("settings.win_alpha"),
                         self._v_win_alpha, 20, 100, "{:.0f} %", preview="hud")

        self._v_speed = tk.IntVar(value=gc.get("snake_speed", 600))
        self._slider_row(hud_f, t("settings.snake_speed"),
                         self._v_speed, 200, 1500, "{:.0f} px/s", preview="hud")

        self._v_lw = tk.IntVar(value=gc.get("line_width_pct", 120))
        self._slider_row(hud_f, t("settings.line_width"),
                         self._v_lw, 30, 360, "{:.0f} %", preview="hud")

        # ── Glow ────────────────────────────────────────────────────────────
        self._section(t("settings.glow"))
        glow_f = tk.Frame(self, bg=BG)
        glow_f.pack(fill="x", padx=24, pady=4)

        self._v_bint = tk.IntVar(value=gc.get("border_intensity", 100))
        self._slider_row(glow_f, t("settings.intensity"),
                         self._v_bint, 0, 100, "{:.0f} %")

        self._v_bdur = tk.DoubleVar(value=gc.get("border_duration", 3.0))
        self._slider_row(glow_f, t("settings.duration"),
                         self._v_bdur, 0.5, 8.0, "{:.1f} s")

        # ── Battery Alerts ───────────────────────────────────────────────────
        self._section(t("settings.alerts"))
        af = tk.Frame(self, bg=BG)
        af.pack(fill="x", padx=24, pady=4)

        self._thresh_section(af, t("settings.alerts_low"),
                             self._low_thresholds,
                             [3, 5, 10, 15, 20, 25])

        tk.Frame(af, bg=BG3, height=1).pack(fill="x", pady=(8, 0))

        self._thresh_section(af, t("settings.alerts_high"),
                             self._high_thresholds,
                             [70, 75, 80, 85, 90])

        tk.Frame(af, bg=BG3, height=1).pack(fill="x", pady=(8, 0))

        self._v_glow_on_low = tk.BooleanVar(
            value=self._data.get("alerts", {}).get("glow_on_low", True))
        tk.Checkbutton(af, text=t("settings.alerts_glow"),
                       variable=self._v_glow_on_low,
                       bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 2))

        # ── Alert HUD position sliders ───────────────────────────────────────
        tk.Frame(af, bg=BG3, height=1).pack(fill="x", pady=(8, 4))
        tk.Label(af, text=t("settings.alert_hud_pos"), bg=BG, fg=GREEN,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self._v_alert_pos_h = tk.IntVar(value=ahc.get("pos_h", 50))
        self._v_alert_pos_v = tk.IntVar(value=ahc.get("pos_v", 50))
        self._slider_row(af, t("settings.alert_pos_h"),
                         self._v_alert_pos_h, 0, 100, "{:.0f} %", preview="none")
        self._slider_row(af, t("settings.alert_pos_v"),
                         self._v_alert_pos_v, 0, 100, "{:.0f} %", preview="none")

        # ── General ─────────────────────────────────────────────────────────
        self._section(t("settings.general"))
        gf = tk.Frame(self, bg=BG)
        gf.pack(fill="x", padx=24, pady=4)

        pf = tk.Frame(gf, bg=BG)
        pf.pack(fill="x", pady=2)
        tk.Label(pf, text=t("settings.poll"), bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(side="left")
        self._v_poll = tk.StringVar(value=str(self._data.get("poll_interval", 30)))
        tk.Entry(pf, textvariable=self._v_poll, width=6, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat").pack(side="left", padx=8)

        self._v_autostart = tk.BooleanVar(value=self._data.get("autostart", False))
        tk.Checkbutton(gf, text=t("settings.autostart"),
                       variable=self._v_autostart,
                       bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w", pady=2)

        # Language selector
        lf = tk.Frame(gf, bg=BG)
        lf.pack(fill="x", pady=(6, 2))
        tk.Label(lf, text=t("settings.language"), bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(side="left")
        self._v_lang = tk.StringVar(value=self._data.get("language", "en"))
        for code, name in LANG_NAMES.items():
            tk.Radiobutton(lf, text=name, variable=self._v_lang, value=code,
                           bg=BG, fg=FG, selectcolor=BG2,
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 10)).pack(side="left", padx=6)
        self._restart_lbl = tk.Label(gf, text="", bg=BG, fg="#888888",
                                     font=("Segoe UI", 9, "italic"))
        self._restart_lbl.pack(anchor="w")
        self._v_lang.trace_add("write", lambda *_: self._restart_lbl.config(
            text=t("settings.restart") if self._v_lang.get() != get_lang() else ""))

        # ── Buttons ─────────────────────────────────────────────────────────
        bf = tk.Frame(self, bg=BG)
        bf.pack(fill="x", padx=16, pady=(12, 16))
        tk.Button(bf, text=t("settings.cancel"), command=self._cancel,
                  bg=BTN, fg=FG, relief="flat", padx=16, pady=6,
                  cursor="hand2").pack(side="right", padx=(4, 0))
        tk.Button(bf, text=t("settings.save"), command=self._save,
                  bg=GREEN, fg="#000000", relief="flat", padx=16, pady=6,
                  cursor="hand2", font=("Segoe UI", 10, "bold")).pack(side="right")

    # ── Preview debounces ─────────────────────────────────────────────────────

    def _schedule_preview(self):
        if not self._on_preview or not self._ready: return
        if self._preview_job: self.after_cancel(self._preview_job)
        self._preview_job = self.after(150, self._do_preview)

    def _do_preview(self):
        self._preview_job = None
        if self._on_preview:
            self._on_preview({"border_intensity": self._v_bint.get(),
                               "border_duration":  round(self._v_bdur.get(), 1)})

    def _schedule_hud_preview(self):
        if not self._on_hud_preview or not self._ready: return
        if self._hud_preview_job: self.after_cancel(self._hud_preview_job)
        self._hud_preview_job = self.after(300, self._do_hud_preview)

    def _do_hud_preview(self):
        self._hud_preview_job = None
        if self._on_hud_preview:
            self._on_hud_preview(self._v_speed.get(), self._v_lw.get(),
                                  self._v_anim_speed.get())

    def _schedule_pos_preview(self):
        if not self._on_pos_preview or not self._ready: return
        if self._pos_preview_job: self.after_cancel(self._pos_preview_job)
        self._pos_preview_job = self.after(80, self._do_pos_preview)

    def _do_pos_preview(self):
        self._pos_preview_job = None
        # Update config temporarily so HudOverlay reads new position
        self._config.data.setdefault("hud", {})
        self._config.data["hud"]["position_v"] = self._v_pos_v.get()
        if self._on_pos_preview:
            self._on_pos_preview()

    # ── Cancel / Save ─────────────────────────────────────────────────────────

    def _cancel(self):
        # Restore any temporarily modified config values
        self._config.data["hud"] = copy.deepcopy(self._data.get("hud", {}))
        self.destroy()

    def _save(self):
        try:
            poll = int(self._v_poll.get())
            assert 5 <= poll <= 3600
        except (ValueError, AssertionError):
            messagebox.showerror("Ungültiger Wert",
                                 "Poll-Intervall muss zwischen 5 und 3600 Sekunden liegen.",
                                 parent=self)
            return

        self._data["poll_interval"] = poll
        self._data["autostart"]     = self._v_autostart.get()
        self._data["language"]      = self._v_lang.get()
        self._data.setdefault("thresholds", {})["low"]  = sorted(self._low_thresholds)
        self._data.setdefault("thresholds", {})["high"] = sorted(self._high_thresholds)
        self._data.setdefault("alerts", {})["glow_on_low"] = self._v_glow_on_low.get()
        self._data["alert_hud"] = {
            "pos_h": self._v_alert_pos_h.get(),
            "pos_v": self._v_alert_pos_v.get(),
        }
        self._data["hud"] = {
            "position_v":   self._v_pos_v.get(),
            "animation":    self._v_anim.get(),
            "anim_speed":   round(self._v_anim_speed.get(), 2),
            "bg_lightness": self._v_bg_light.get(),
            "win_alpha":    self._v_win_alpha.get(),
        }
        self._data["glow"] = {
            "snake_speed":      self._v_speed.get(),
            "line_width_pct":   self._v_lw.get(),
            "border_intensity": self._v_bint.get(),
            "border_duration":  round(self._v_bdur.get(), 1),
        }
        self._config.data = self._data
        self._config.save()
        try:
            set_autostart(self._data["autostart"])
        except Exception:
            pass
        lang_changed = self._v_lang.get() != get_lang()
        self._on_save()
        self.destroy()
        if lang_changed:
            import os, sys
            os.execv(sys.executable, [sys.executable] + sys.argv)
