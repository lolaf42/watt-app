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
                 on_save: Callable, on_preview: Callable = None):
        super().__init__(parent)
        self.title("Watt — Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._config     = config
        self._on_save    = on_save
        self._on_preview = on_preview
        self._preview_job: str | None = None
        self._ready      = False
        self._data = copy.deepcopy(config.data)

        self._build()
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.after(300, lambda: setattr(self, '_ready', True))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, title: str) -> tk.Frame:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(outer, text=title, bg=BG, fg=GREEN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Frame(outer, bg=BG3, height=1).pack(fill="x", pady=(3, 0))
        return outer

    def _slider_row(self, parent, label, var, from_, to, fmt):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG,
                 font=("Segoe UI", 10), width=26, anchor="w").pack(side="left")
        val_lbl = tk.Label(row, bg=BG, fg=GREEN,
                           font=("Segoe UI", 10), width=7, anchor="e")
        val_lbl.pack(side="right")
        def _upd(v, lbl=val_lbl, f=fmt):
            lbl.config(text=f.format(float(v)))
            self._schedule_preview()
        sl = tk.Scale(row, variable=var, from_=from_, to=to,
                      orient="horizontal", bg=BG, fg=FG,
                      troughcolor=BG3, highlightthickness=0,
                      sliderrelief="flat", showvalue=False,
                      command=_upd, length=180)
        sl.pack(side="left", padx=6)
        val_lbl.config(text=fmt.format(float(var.get())))

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _option_row(self, parent: tk.Frame, label: str,
                    var: tk.StringVar, choices: list[tuple[str, str]]):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG,
                 font=("Segoe UI", 10), width=26, anchor="w").pack(side="left")
        display_values = [c[0] for c in choices]
        key_map = {c[0]: c[1] for c in choices}
        rev_map = {c[1]: c[0] for c in choices}
        var_display = tk.StringVar(value=rev_map.get(var.get(), display_values[0]))
        def _on_change(*_):
            var.set(key_map[var_display.get()])
        var_display.trace_add("write", _on_change)
        menu = tk.OptionMenu(row, var_display, *display_values)
        menu.config(bg=BG2, fg=FG, activebackground=BG3, activeforeground=FG,
                    relief="flat", highlightthickness=0, font=("Segoe UI", 10))
        menu["menu"].config(bg=BG2, fg=FG, activebackground=BG3,
                            activeforeground=FG, font=("Segoe UI", 10))
        menu.pack(side="left", padx=6)

    def _build(self):
        gc = self._data.get("glow", {})

        # ── HUD ─────────────────────────────────────────────────────────────
        self._section("HUD Window")
        hud_f = tk.Frame(self, bg=BG)
        hud_f.pack(fill="x", padx=24, pady=4)
        hc = self._data.get("hud", {})

        self._v_pos_v = tk.StringVar(value=hc.get("position_v", "top"))
        self._option_row(hud_f, "Vertical position:",
                         self._v_pos_v,
                         [("Oben", "top"), ("Mitte", "center"), ("Unten", "bottom")])

        self._v_pos_h = tk.StringVar(value=hc.get("position_h", "center"))
        self._option_row(hud_f, "Horizontal position:",
                         self._v_pos_h,
                         [("Links", "left"), ("Mitte", "center"), ("Rechts", "right")])

        self._v_anim = tk.StringVar(value=hc.get("animation", "bounce"))
        self._option_row(hud_f, "Animation:",
                         self._v_anim,
                         [("Aufspringen", "bounce"), ("Einblenden", "fade"),
                          ("Batterie-Füllung", "fill"), ("Kein", "none")])

        # ── Glow Animation ──────────────────────────────────────────────────
        self._section("Glow Animation")
        glow_f = tk.Frame(self, bg=BG)
        glow_f.pack(fill="x", padx=24, pady=4)

        self._v_bint = tk.IntVar(value=gc.get("border_intensity", 100))
        self._slider_row(glow_f, "Screen border intensity (%):",
                         self._v_bint, 0, 100, "{:.0f} %")

        self._v_bdur = tk.DoubleVar(value=gc.get("border_duration", 1.5))
        self._slider_row(glow_f, "Border glow duration (s):",
                         self._v_bdur, 0.5, 8.0, "{:.1f} s")

        # ── General ─────────────────────────────────────────────────────────
        self._section("General")
        gf = tk.Frame(self, bg=BG)
        gf.pack(fill="x", padx=24, pady=4)

        pf = tk.Frame(gf, bg=BG)
        pf.pack(fill="x", pady=2)
        tk.Label(pf, text="Poll interval (seconds):", bg=BG, fg=FG,
                 font=("Segoe UI", 10)).pack(side="left")
        self._v_poll = tk.StringVar(value=str(self._data.get("poll_interval", 30)))
        tk.Entry(pf, textvariable=self._v_poll, width=6, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat").pack(side="left", padx=8)

        self._v_autostart = tk.BooleanVar(value=self._data.get("autostart", False))
        tk.Checkbutton(gf, text="Start automatically at login",
                       variable=self._v_autostart,
                       bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w", pady=2)

        # ── Buttons ─────────────────────────────────────────────────────────
        bf = tk.Frame(self, bg=BG)
        bf.pack(fill="x", padx=16, pady=(12, 16))
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg=BTN, fg=FG, relief="flat", padx=16, pady=6,
                  cursor="hand2").pack(side="right", padx=(4, 0))
        tk.Button(bf, text="Save", command=self._save,
                  bg=GREEN, fg="#000000", relief="flat", padx=16, pady=6,
                  cursor="hand2", font=("Segoe UI", 10, "bold")).pack(side="right")

    # ── Live preview ─────────────────────────────────────────────────────────

    def _schedule_preview(self):
        if not self._on_preview or not self._ready:
            return
        if self._preview_job:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(150, self._do_preview)

    def _do_preview(self):
        self._preview_job = None
        if self._on_preview:
            self._on_preview({
                "snake_speed":      self._v_speed.get(),
                "line_width":       self._v_lw.get(),
                "border_intensity": self._v_bint.get(),
                "border_duration":  round(self._v_bdur.get(), 1),
            })

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save(self):
        try:
            poll = int(self._v_poll.get())
            assert 5 <= poll <= 3600
        except (ValueError, AssertionError):
            messagebox.showerror("Invalid value",
                                 "Poll interval must be between 5 and 3600 seconds.",
                                 parent=self)
            return

        self._data["poll_interval"] = poll
        self._data["autostart"] = self._v_autostart.get()
        self._data["hud"] = {
            "position_v": self._v_pos_v.get(),
            "position_h": self._v_pos_h.get(),
            "animation":  self._v_anim.get(),
        }
        self._data["glow"] = {
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
