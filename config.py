"""Persistent JSON config, stored in platform-appropriate location."""

import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT: dict = {
    "language": "en",
    "poll_interval": 30,
    "thresholds": {
        "low": [5, 10, 20],
        "high": [80],
    },
    "alerts": {
        "plugged": True,
        "unplugged": True,
        "threshold_low": True,
        "threshold_high": True,
    },
    "autostart": False,
    "notification_sound": True,
    "glow": {
        "snake_speed":       600,   # px/s  (200–1500)
        "line_width_pct":    120,   # %     (30–360, 30%=1px)
        "border_intensity":  100,   # %     (0–100)
        "border_duration":   3.0,   # s     (0.5–8)
    },
    "hud": {
        "position_v":       5,        # 0 (top) – 100 (bottom)
        "position_h":      50,        # 0 (left) – 100 (right)
        "animation":   "bounce",      # none / fade / bounce
        "anim_speed":     1.0,        # multiplier 0.25 – 3.0
    },
}


def _config_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", Path.home())
        return Path(base) / "watt-app"
    return Path.home() / ".config" / "watt-app"


class ConfigManager:
    def __init__(self):
        self._path = _config_dir() / "config.json"
        self.data: dict = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path) as f:
                    return _merge(DEFAULT, json.load(f))
            except Exception:
                pass
        return _merge(DEFAULT, {})

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


def _merge(defaults: dict, overrides: dict) -> dict:
    result = dict(defaults)
    for k, v in overrides.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result
