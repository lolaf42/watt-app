"""Persistent JSON config, stored in platform-appropriate location."""

import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT: dict = {
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
        "line_width":          4,   # px    (1–20)
        "border_intensity":  100,   # %     (0–100)
        "border_duration":   1.5,   # s     (0.5–8)
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
