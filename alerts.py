"""Alert state machine: fires once per threshold crossing, resets with hysteresis."""

import logging
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

    def reset(self):
        self._fired_low.clear()
        self._fired_high.clear()

    def check(self, state: BatteryState) -> list[tuple[str, str, str]]:
        """Return list of (title, message, level) notifications to send.

        level is one of: 'critical', 'warning', 'high', 'info'
        """
        if not state.has_battery:
            return []

        alerts: list[tuple[str, str, str]] = []
        cfg = self._config.data
        ac = cfg.get("alerts", {})
        th = cfg.get("thresholds", {})

        # ── Low thresholds (discharging below %) ────────────────────────────
        if ac.get("threshold_low", True) and not state.is_charging:
            for thresh in sorted(th.get("low", []), reverse=True):
                if state.percent <= thresh and thresh not in self._fired_low:
                    self._fired_low.add(thresh)
                    sub = (t("alert.low_critical") if state.percent <= 5
                           else t("alert.low_time", time=state.time_remaining_text))
                    level = "critical" if state.percent <= 5 else "warning"
                    alerts.append((t("alert.low", pct=state.percent), sub, level))
                elif state.percent > thresh + HYSTERESIS:
                    self._fired_low.discard(thresh)

        # ── High thresholds (charging above %) ──────────────────────────────
        if ac.get("threshold_high", True) and state.is_charging:
            for thresh in sorted(th.get("high", [])):
                if state.percent >= thresh and thresh not in self._fired_high:
                    self._fired_high.add(thresh)
                    alerts.append((t("alert.high", pct=state.percent),
                                   t("alert.high_msg"), "high"))
                elif state.percent < thresh - HYSTERESIS:
                    self._fired_high.discard(thresh)

        return alerts
