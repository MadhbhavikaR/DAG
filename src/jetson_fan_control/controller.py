"""Fan-curve logic and sysfs access."""

from __future__ import annotations

from pathlib import Path

from jetson_fan_control.config import FanConfig

DEFAULT_TEMP_PATH = Path("/sys/devices/virtual/thermal/thermal_zone0/temp")
DEFAULT_PWM_PATH = Path("/sys/devices/pwm-fan/target_pwm")


class FanController:
    """Read a thermal sensor and set the fan's PWM target."""

    def __init__(
        self,
        config: FanConfig,
        temperature_path: Path = DEFAULT_TEMP_PATH,
        pwm_path: Path = DEFAULT_PWM_PATH,
    ) -> None:
        self.config = config
        self.temperature_path = temperature_path
        self.pwm_path = pwm_path
        self._last_speed: int | None = None

    @staticmethod
    def fan_curve(temperature: float, off_temp: float, max_temp: float) -> int:
        """Map temperature to the Linux PWM range (0-255), linearly clamped."""
        if max_temp <= off_temp:
            raise ValueError("max_temp must be greater than off_temp.")
        if temperature <= off_temp:
            return 0
        if temperature >= max_temp:
            return 255
        return int(255 * (temperature - off_temp) / (max_temp - off_temp))

    def read_temperature(self) -> float:
        """Read the thermal zone value, expressed in millidegrees Celsius."""
        raw = self.temperature_path.read_text(encoding="ascii").strip()
        return int(raw) / 1000.0

    def set_speed(self, speed: int) -> None:
        """Write a validated PWM value to the sysfs control."""
        if not 0 <= speed <= 255:
            raise ValueError("PWM speed must be between 0 and 255.")
        self.pwm_path.write_text(str(speed), encoding="ascii")

    def update(self) -> tuple[float, int, bool]:
        """Apply one update and return the temperature, speed, and changed flag."""
        temperature = self.read_temperature()
        speed = self.fan_curve(
            temperature,
            self.config.fan_off_temp,
            self.config.fan_max_temp,
        )
        changed = speed != self._last_speed
        if changed:
            self.set_speed(speed)
            self._last_speed = speed
        return temperature, speed, changed
