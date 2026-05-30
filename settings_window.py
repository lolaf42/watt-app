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
DIM = "#8B949E"
GREEN = "#00CC00"
RED = "#DC3232"
BTN = "#21262D"


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: tk.Tk, config: ConfigManager, on_save: Callable):
        super().__init__(parent)
        self.title("Watt — Settings")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._config = config
        self._on_save = on_save
        self._data = copy.deepcopy(config.data)

        self._build()
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, title: str) -> tk.Frame:
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(outer, text=title, bg=BG, fg=GREEN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Frame(outer, bg=BG3, height=1).pack(fill="x", pady=(3, 0))
        return outer

    def _check(self, parent: tk.Frame, text: str, var: tk.BooleanVar):
        tk.Checkbutton(parent, text=text, variable=var,
                       bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).pack(anchor="w", pady=2)

    def _threshold_row(self, parent: tk.Frame, value: int, remove_cmd: Callable):
        f = tk.Frame(parent, bg=BG2)
        f.pack(fill="x", pady=1)
        tk.Label(f, text=f"  {value}%", bg=BG2, fg=FG,
                 font=("Segoe UI", 10), width=8, anchor="w").pack(side="left")
        tk.Button(f, text="✕", command=remove_cmd,
                  bg=BG2, fg=RED, relief="flat", padx=6,
                  cursor="hand2", font=("Segoe UI", 9)).pack(side="right")

    def _add_entry(self, parent: tk.Frame, entry_var: tk.StringVar,
                   cmd: Callable) -> tk.Entry:
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", pady=(6, 0))
        e = tk.Entry(f, textvariable=entry_var, width=6, bg=BG2, fg=FG,
                     insertbackground=FG, relief="flat", font=("Segoe UI", 10))
        e.pack(side="left", padx=(0, 6))
        tk.Button(f, text="Add", command=cmd, bg=BTN, fg=FG,
                  relief="flat", padx=10, cursor="hand2").pack(side="left")
        return e

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        th = self._data["thresholds"]

        # ── Low thresholds ──────────────────────────────────────────────────
        self._section("Low Battery Thresholds (%)")
        low_wrap = tk.Frame(self, bg=BG)
        low_wrap.pack(fill="x", padx=20, pady=2)
        self._low_list = tk.Frame(low_wrap, bg=BG)
        self._low_list.pack(fill="x")
        self._render_low()
        self._low_entry_var = tk.StringVar()
        self._add_entry(low_wrap, self._low_entry_var, self._add_low)

        # ── High thresholds ─────────────────────────────────────────────────
        self._section("Charge Alert Thresholds (%)")
        high_wrap = tk.Frame(self, bg=BG)
        high_wrap.pack(fill="x", padx=20, pady=2)
        self._high_list = tk.Frame(high_wrap, bg=BG)
        self._high_list.pack(fill="x")
        self._render_high()
        self._high_entry_var = tk.StringVar()
        self._add_entry(high_wrap, self._high_entry_var, self._add_high)

        # ── Alert types ─────────────────────────────────────────────────────
        self._section("Alert Types")
        af = tk.Frame(self, bg=BG)
        af.pack(fill="x", padx=24, pady=4)
        ac = self._data["alerts"]
        self._v_plugged = tk.BooleanVar(value=ac.get("plugged", True))
        self._v_unplugged = tk.BooleanVar(value=ac.get("unplugged", True))
        self._v_low = tk.BooleanVar(value=ac.get("threshold_low", True))
        self._v_high = tk.BooleanVar(value=ac.get("threshold_high", True))
        self._check(af, "Alert when charger is connected", self._v_plugged)
        self._check(af, "Alert when charger is disconnected", self._v_unplugged)
        self._check(af, "Alert on low battery thresholds", self._v_low)
        self._check(af, "Alert on high charge thresholds", self._v_high)

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
        self._check(gf, "Start automatically at login", self._v_autostart)

        # ── Buttons ─────────────────────────────────────────────────────────
        bf = tk.Frame(self, bg=BG)
        bf.pack(fill="x", padx=16, pady=(12, 16))
        tk.Button(bf, text="Cancel", command=self.destroy,
                  bg=BTN, fg=FG, relief="flat", padx=16, pady=6,
                  cursor="hand2").pack(side="right", padx=(4, 0))
        tk.Button(bf, text="Save", command=self._save,
                  bg=GREEN, fg="#000000", relief="flat", padx=16, pady=6,
                  cursor="hand2", font=("Segoe UI", 10, "bold")).pack(side="right")

    # ── Threshold management ──────────────────────────────────────────────────

    def _render_low(self):
        for w in self._low_list.winfo_children():
            w.destroy()
        for t in sorted(self._data["thresholds"]["low"]):
            self._threshold_row(self._low_list, t, lambda v=t: self._rm_low(v))

    def _render_high(self):
        for w in self._high_list.winfo_children():
            w.destroy()
        for t in sorted(self._data["thresholds"]["high"]):
            self._threshold_row(self._high_list, t, lambda v=t: self._rm_high(v))

    def _add_low(self):
        try:
            v = int(self._low_entry_var.get().strip())
            if 1 <= v <= 99 and v not in self._data["thresholds"]["low"]:
                self._data["thresholds"]["low"].append(v)
                self._render_low()
                self._low_entry_var.set("")
        except ValueError:
            pass

    def _rm_low(self, v: int):
        self._data["thresholds"]["low"].remove(v)
        self._render_low()

    def _add_high(self):
        try:
            v = int(self._high_entry_var.get().strip())
            if 1 <= v <= 100 and v not in self._data["thresholds"]["high"]:
                self._data["thresholds"]["high"].append(v)
                self._render_high()
                self._high_entry_var.set("")
        except ValueError:
            pass

    def _rm_high(self, v: int):
        self._data["thresholds"]["high"].remove(v)
        self._render_high()

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
        self._data["alerts"] = {
            "plugged": self._v_plugged.get(),
            "unplugged": self._v_unplugged.get(),
            "threshold_low": self._v_low.get(),
            "threshold_high": self._v_high.get(),
        }

        self._config.data = self._data
        self._config.save()

        try:
            set_autostart(self._data["autostart"])
        except Exception:
            pass

        self._on_save()
        self.destroy()
