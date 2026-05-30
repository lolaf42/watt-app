"""Alert state machine: fires once per threshold crossing, resets with hysteresis."""

import logging
from typing import Optional

from battery import BatteryState
from config import ConfigManager
from i18n import t

logger = logging.getLogger(__name__)

HYSTERESIS = 2  # percent — threshold resets when battery crosses back by this much


class AlertManager:
    def __init__(self, config: ConfigManager):
        self._config = config
        self._fired_low: set[int] = set()
        self._fired_high: set[int] = set()
        self._prev_plugged: Optional[bool] = None

    def reset(self):
        self._fired_low.clear()
        self._fired_high.clear()

    def check(self, state: BatteryState) -> list[tuple[str, str]]:
        """Return list of (title, message) notifications to send."""
        if not state.has_battery:
            return []

        alerts: list[tuple[str, str]] = []
        cfg = self._config.data
        ac = cfg.get("alerts", {})
        th = cfg.get("thresholds", {})

        # ── Plug / unplug ───────────────────────────────────────────────────
        if self._prev_plugged is not None and state.is_plugged != self._prev_plugged:
            if state.is_plugged and ac.get("plugged", True):
                alerts.append((t("alert.connected"),
                                t("alert.connected_msg", pct=state.percent)))
            elif not state.is_plugged and ac.get("unplugged", True):
                alerts.append((t("alert.disconnected"),
                                t("alert.disconnected_msg", pct=state.percent)))
        self._prev_plugged = state.is_plugged

        # ── Low thresholds (discharging below %) ────────────────────────────
        if ac.get("threshold_low", True) and not state.is_charging:
            for t in sorted(th.get("low", []), reverse=True):
                if state.percent <= t and t not in self._fired_low:
                    self._fired_low.add(t)
                    sub = (t("alert.low_critical") if state.percent <= 5
                           else t("alert.low_time", time=state.time_remaining_text))
                    alerts.append((t("alert.low", pct=state.percent), sub))
                elif state.percent > t + HYSTERESIS:
                    self._fired_low.discard(t)

        # ── High thresholds (charging above %) ──────────────────────────────
        if ac.get("threshold_high", True) and state.is_charging:
            for t in sorted(th.get("high", [])):
                if state.percent >= t and t not in self._fired_high:
                    self._fired_high.add(t)
                    alerts.append((t("alert.high", pct=state.percent),
                                   t("alert.high_msg")))
                elif state.percent < t - HYSTERESIS:
                    self._fired_high.discard(t)

        return alerts
