"""Tests for JSON configuration parsing."""

import json
from pathlib import Path

import pytest

from jetson_fan_control.config import FanConfig


def test_load_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "FAN_OFF_TEMP": 22,
                "FAN_MAX_TEMP": 65,
                "UPDATE_INTERVAL": 1.5,
                "MAX_PERF": 1,
            }
        ),
        encoding="utf-8",
    )
    config = FanConfig.from_file(path)
    assert config.fan_off_temp == 22
    assert config.fan_max_temp == 65
    assert config.update_interval == 1.5
    assert config.max_perf is True


def test_invalid_temperature_range_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"FAN_OFF_TEMP": 50, "FAN_MAX_TEMP": 50}', encoding="utf-8")
    with pytest.raises(ValueError, match="FAN_MAX_TEMP"):
        FanConfig.from_file(path)


def test_invalid_update_interval_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{"UPDATE_INTERVAL": 0}', encoding="utf-8")
    with pytest.raises(ValueError, match="UPDATE_INTERVAL"):
        FanConfig.from_file(path)
