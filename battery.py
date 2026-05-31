"""Battery data reading — Linux (/sys/class/power_supply/) and Windows (psutil + WMI)."""

import os
import sys
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BatteryState:
    has_battery: bool = False
    percent: int = 0
    is_charging: bool = False
    is_plugged: bool = False
    is_full: bool = False
    seconds_remaining: Optional[int] = None
    health_percent: Optional[float] = None
    cycle_count: Optional[int] = None
    temperature_celsius: Optional[float] = None
    temperature_is_battery: bool = False   # True = real battery temp, False = board/system
    voltage_mv: Optional[int] = None
    current_ma: Optional[int] = None
    power_watts: Optional[float] = None
    design_capacity_mwh: Optional[int] = None
    full_capacity_mwh: Optional[int] = None
    remaining_mwh: Optional[int] = None

    @property
    def time_remaining_text(self) -> str:
        if self.seconds_remaining is None or self.seconds_remaining < 0:
            return "Calculating..."
        h = self.seconds_remaining // 3600
        m = (self.seconds_remaining % 3600) // 60
        return f"{h}h {m}min" if h > 0 else f"{m}min"

    @property
    def status_text(self) -> str:
        if not self.has_battery:
            return "No battery"
        if self.is_full:
            return "Full"
        return "Charging" if self.is_charging else "Discharging"

    @property
    def health_label(self) -> str:
        if self.health_percent is None:
            return "Unknown"
        if self.health_percent >= 80:
            return "Good"
        if self.health_percent >= 60:
            return "Fair"
        return "Poor"


def get_battery_state() -> BatteryState:
    if sys.platform == "win32":
        return _get_windows_battery()
    return _get_linux_battery()


# ── Linux ──────────────────────────────────────────────────────────────────────

_SYS_PS = "/sys/class/power_supply"


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    v = _read(path)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _read_board_temp() -> Optional[float]:
    """Read chassis/board ambient temperature from hwmon (cros_ec local sensor, etc.)."""
    try:
        base = "/sys/class/hwmon"
        for dev in sorted(os.listdir(base)):
            name = _read(f"{base}/{dev}/name") or ""
            # Framework EC: local_f75303 is the board ambient sensor
            if name == "cros_ec":
                for i in range(1, 6):
                    label = _read(f"{base}/{dev}/temp{i}_label") or ""
                    if "local" in label.lower():
                        raw = _read_int(f"{base}/{dev}/temp{i}_input")
                        if raw and 5_000 < raw < 90_000:
                            return raw / 1000.0
    except Exception:
        pass
    return None


def _find_battery() -> Optional[str]:
    try:
        for name in sorted(os.listdir(_SYS_PS)):
            path = os.path.join(_SYS_PS, name)
            if _read(os.path.join(path, "type")) == "Battery":
                return path
    except OSError:
        pass
    return None


def _get_linux_battery() -> BatteryState:
    bat = _find_battery()

    if bat is None:
        # Fallback: psutil
        try:
            import psutil
            b = psutil.sensors_battery()
            if b is None:
                return BatteryState(has_battery=False)
            pct = int(b.percent)
            return BatteryState(
                has_battery=True,
                percent=pct,
                is_plugged=b.power_plugged,
                is_charging=b.power_plugged and pct < 99,
                is_full=b.power_plugged and pct >= 99,
                seconds_remaining=b.secsleft if b.secsleft >= 0 else None,
            )
        except Exception:
            return BatteryState(has_battery=False)

    status = _read(os.path.join(bat, "status")) or "Unknown"
    capacity = _read_int(os.path.join(bat, "capacity")) or 0

    is_charging = status == "Charging"
    is_full = status == "Full" or capacity >= 99
    is_plugged = is_charging or is_full

    # Energy (µWh) preferred; fall back to charge (µAh) × nominal voltage
    e_now = _read_int(os.path.join(bat, "energy_now"))
    e_full = _read_int(os.path.join(bat, "energy_full"))
    e_design = _read_int(os.path.join(bat, "energy_full_design"))

    if e_now is None:
        c_now    = _read_int(os.path.join(bat, "charge_now"))
        c_full   = _read_int(os.path.join(bat, "charge_full"))
        c_design = _read_int(os.path.join(bat, "charge_full_design"))
        # Use nominal (design) voltage for accurate Wh — matches upower
        v_nom = (_read_int(os.path.join(bat, "voltage_min_design"))
                 or _read_int(os.path.join(bat, "voltage_now"))
                 or 3_700_000)
        if c_now is not None:
            e_now = c_now * v_nom // 1_000_000
        if c_full is not None:
            e_full = c_full * v_nom // 1_000_000
        if c_design is not None:
            e_design = c_design * v_nom // 1_000_000

    health = None
    if e_full and e_design and e_design > 0:
        health = e_full * 100.0 / e_design

    # Time remaining from power_now (µW)
    p_now = _read_int(os.path.join(bat, "power_now"))
    seconds = None
    if p_now and p_now > 0 and e_now is not None:
        if is_charging and e_full:
            seconds = int((e_full - e_now) * 3600 / p_now)
        elif not is_charging:
            seconds = int(e_now * 3600 / p_now)

    temp_raw  = _read_int(os.path.join(bat, "temp"))
    temp_c    = (temp_raw / 10.0 if temp_raw is not None
                 else _read_board_temp())
    v_now_raw = _read_int(os.path.join(bat, "voltage_now"))
    c_now_raw = _read_int(os.path.join(bat, "current_now"))
    cycle     = _read_int(os.path.join(bat, "cycle_count"))

    return BatteryState(
        has_battery=True,
        percent=capacity,
        is_charging=is_charging,
        is_plugged=is_plugged,
        is_full=is_full,
        seconds_remaining=seconds,
        health_percent=health,
        cycle_count=cycle,
        temperature_celsius=temp_c,
        temperature_is_battery=(temp_raw is not None),
        voltage_mv=v_now_raw // 1000 if v_now_raw else None,
        current_ma=c_now_raw // 1000 if c_now_raw else None,
        power_watts=(p_now / 1_000_000 if p_now
                     else (c_now_raw * v_now_raw / 1_000_000_000_000)
                          if c_now_raw and v_now_raw else None),
        remaining_mwh=e_now // 1000 if e_now else None,
        full_capacity_mwh=e_full // 1000 if e_full else None,
        design_capacity_mwh=e_design // 1000 if e_design else None,
    )


# ── Windows ────────────────────────────────────────────────────────────────────

def _get_windows_battery() -> BatteryState:
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is None:
            return BatteryState(has_battery=False)

        pct = int(b.percent)
        is_plugged = b.power_plugged
        is_full = is_plugged and pct >= 99
        is_charging = is_plugged and not is_full
        secs = b.secsleft if b.secsleft >= 0 else None

        state = BatteryState(
            has_battery=True,
            percent=pct,
            is_charging=is_charging,
            is_plugged=is_plugged,
            is_full=is_full,
            seconds_remaining=secs,
        )
        try:
            state = _enrich_wmi(state)
        except Exception:
            pass
        return state
    except Exception as e:
        logger.debug(f"Windows battery read failed: {e}")
        return BatteryState(has_battery=False)


def _enrich_wmi(state: BatteryState) -> BatteryState:
    ps = (
        "Get-CimInstance Win32_Battery | "
        "Select-Object DesignCapacity,FullChargeCapacity,CycleCount | "
        "ConvertTo-Json -Compress"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=5,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return state
    data = json.loads(r.stdout.strip())
    if isinstance(data, list):
        data = data[0] if data else {}

    design = data.get("DesignCapacity")
    full = data.get("FullChargeCapacity")
    cycles = data.get("CycleCount")
    health = full * 100.0 / design if design and full and design > 0 else None

    from dataclasses import replace
    return replace(
        state,
        health_percent=health,
        cycle_count=cycles,
        design_capacity_mwh=design,
        full_capacity_mwh=full,
    )
