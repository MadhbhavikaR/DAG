"""Configuration loading and validation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FanConfig:
    """Validated fan controller settings."""

    fan_off_temp: float = 20.0
    fan_max_temp: float = 50.0
    update_interval: float = 2.0
    max_perf: bool = False

    @classmethod
    def from_file(cls, path: Path) -> FanConfig:
        """Load and validate settings from a JSON file."""
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(
                f"Cannot read configuration file {path}: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in configuration file {path}: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise ValueError("Configuration must be a JSON object.")

        try:
            off_temp = float(raw.get("FAN_OFF_TEMP", 20.0))
            max_temp = float(raw.get("FAN_MAX_TEMP", 50.0))
            interval = float(raw.get("UPDATE_INTERVAL", 2.0))
            max_perf_value = raw.get("MAX_PERF", False)
            if isinstance(max_perf_value, str):
                raise ValueError(
                    "MAX_PERF must be a boolean or number, not a string."
                )
            config = cls(
                fan_off_temp=off_temp,
                fan_max_temp=max_temp,
                update_interval=interval,
                max_perf=bool(max_perf_value),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Configuration values must be numeric; MAX_PERF may be boolean."
            ) from exc

        config.validate()
        return config

    def validate(self) -> None:
        """Reject values that would make the controller unusable."""
        values = (self.fan_off_temp, self.fan_max_temp, self.update_interval)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(
                "Temperature thresholds and UPDATE_INTERVAL must be finite."
            )
        if self.fan_max_temp <= self.fan_off_temp:
            raise ValueError("FAN_MAX_TEMP must be greater than FAN_OFF_TEMP.")
        if self.update_interval <= 0:
            raise ValueError("UPDATE_INTERVAL must be greater than zero.")
