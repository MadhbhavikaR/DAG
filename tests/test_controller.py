"""Tests for the temperature-to-PWM control behavior."""

from pathlib import Path

import pytest

from jetson_fan_control.config import FanConfig
from jetson_fan_control.controller import FanController


@pytest.mark.parametrize(
    ("temperature", "expected"),
    [(10, 0), (20, 0), (35, 127), (50, 255), (75, 255)],
)
def test_fan_curve_clamps_and_interpolates(temperature: float, expected: int) -> None:
    assert FanController.fan_curve(temperature, 20, 50) == expected


def test_fan_curve_rejects_invalid_temperature_range() -> None:
    with pytest.raises(ValueError):
        FanController.fan_curve(20, 30, 30)


def test_update_only_writes_changed_speed(tmp_path: Path) -> None:
    temperature_path = tmp_path / "temperature"
    pwm_path = tmp_path / "pwm"
    temperature_path.write_text("35000", encoding="ascii")
    pwm_path.write_text("", encoding="ascii")
    config = FanConfig(fan_off_temp=20, fan_max_temp=50, update_interval=2)

    controller = FanController(config, temperature_path, pwm_path)
    assert controller.update() == (35.0, 127, True)
    assert pwm_path.read_text(encoding="ascii") == "127"
    assert controller.update() == (35.0, 127, False)


def test_temperature_reading_uses_millidegrees(tmp_path: Path) -> None:
    temperature_path = tmp_path / "temperature"
    temperature_path.write_text("42750\n", encoding="ascii")
    controller = FanController(FanConfig(), temperature_path, tmp_path / "pwm")
    assert controller.read_temperature() == 42.75
