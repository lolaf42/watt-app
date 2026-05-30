"""Settings window — tkinter, dark themed."""

import copy
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from config import ConfigManager
from autostart import set_autostart

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
        self.title("Watt — Settings")
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
            else:
                self._schedule_preview()
        sl = tk.Scale(row, variable=var, from_=from_, to=to,
                      orient="horizontal", bg=BG, fg=FG,
                      troughcolor=BG3, highlightthickness=0,
                      sliderrelief="flat", showvalue=False,
                      command=_upd, length=180)
        sl.pack(side="left", padx=6)
        val_lbl.config(text=fmt.format(float(var.get())))

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        hc = self._data.get("hud", {})
        gc = self._data.get("glow", {})

        # ── HUD Window ──────────────────────────────────────────────────────
        self._section("HUD Window")
        hud_f = tk.Frame(self, bg=BG)
        hud_f.pack(fill="x", padx=24, pady=4)

        self._v_pos_v = tk.IntVar(value=hc.get("position_v", 5))
        self._slider_row(hud_f, "Position vertikal (%):",
                         self._v_pos_v, 0, 100, "{:.0f} %", preview="pos")

        self._v_pos_h = tk.IntVar(value=hc.get("position_h", 50))
        self._slider_row(hud_f, "Position horizontal (%):",
                         self._v_pos_h, 0, 100, "{:.0f} %", preview="pos")

        self._v_anim = tk.StringVar(value=hc.get("animation", "bounce"))
        anim_row = tk.Frame(hud_f, bg=BG)
        anim_row.pack(fill="x", pady=4)
        tk.Label(anim_row, text="Animation:", bg=BG, fg=FG,
                 font=("Segoe UI", 10), width=26, anchor="w").pack(side="left")
        for key, label in [("bounce","Aufspringen"),("fade","Einblenden"),("none","Kein")]:
            tk.Radiobutton(anim_row, text=label, variable=self._v_anim, value=key,
                           bg=BG, fg=FG, selectcolor=BG2,
                           activebackground=BG, activeforeground=FG,
                           font=("Segoe UI", 10)).pack(side="left", padx=6)

        self._v_anim_speed = tk.DoubleVar(value=hc.get("anim_speed", 1.0))
        self._slider_row(hud_f, "Animationsgeschwindigkeit:",
                         self._v_anim_speed, 0.25, 3.0, "{:.2f}×", preview="hud")

        self._v_speed = tk.IntVar(value=gc.get("snake_speed", 600))
        self._slider_row(hud_f, "Snake-Geschwindigkeit (px/s):",
                         self._v_speed, 200, 1500, "{:.0f} px/s", preview="hud")

        self._v_lw = tk.IntVar(value=gc.get("line_width_pct", 120))
        self._slider_row(hud_f, "Liniendicke:",
                         self._v_lw, 30, 360, "{:.0f} %", preview="hud")

        # ── Glow Animation ──────────────────────────────────────────────────
        self._section("Bildschirmrand-Glow")
        glow_f = tk.Frame(self, bg=BG)
        glow_f.pack(fill="x", padx=24, pady=4)

        self._v_bint = tk.IntVar(value=gc.get("border_intensity", 100))
        self._slider_row(glow_f, "Intensität (%):",
                         self._v_bint, 0, 100, "{:.0f} %")

        self._v_bdur = tk.DoubleVar(value=gc.get("border_duration", 3.0))
        self._slider_row(glow_f, "Dauer (s):",
                         self._v_bdur, 0.5, 8.0, "{:.1f} s")

        # ── General ─────────────────────────────────────────────────────────
        self._section("Allgemein")
        gf = tk.Frame(self, bg=BG)
        gf.pack(fill="x", padx=24, pady=4)

        pf = tk.Frame(gf, bg=BG)
        pf.pack(fill="x", pady=2)
        tk.Label(pf, text="Poll-Intervall (Sek.):", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(side="left")
        self._v_poll = tk.StringVar(value=str(self._data.get("poll_interval", 30)))
        tk.Entry(pf, textvariable=self._v_poll, width=6, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat").pack(side="left", padx=8)

        self._v_autostart = tk.BooleanVar(value=self._data.get("autostart", False))
        tk.Checkbutton(gf, text="Automatisch beim Anmelden starten",
                       variable=self._v_autostart,
                       bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w", pady=2)

        # ── Buttons ─────────────────────────────────────────────────────────
        bf = tk.Frame(self, bg=BG)
        bf.pack(fill="x", padx=16, pady=(12, 16))
        tk.Button(bf, text="Abbrechen", command=self._cancel,
                  bg=BTN, fg=FG, relief="flat", padx=16, pady=6,
                  cursor="hand2").pack(side="right", padx=(4, 0))
        tk.Button(bf, text="Speichern", command=self._save,
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
        self._config.data["hud"]["position_h"] = self._v_pos_h.get()
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
        self._data["hud"] = {
            "position_v":  self._v_pos_v.get(),
            "position_h":  self._v_pos_h.get(),
            "animation":   self._v_anim.get(),
            "anim_speed":  round(self._v_anim_speed.get(), 2),
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
        self._on_save()
        self.destroy()
