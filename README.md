# Jetson Nano Fan Control

A small, configurable fan controller for the NVIDIA Jetson Nano (4 GB). It reads the board's thermal sensor, maps temperature to PWM duty cycle, and updates the fan only when the requested speed changes. It can run as a systemd service so cooling starts automatically after boot.

This utility is maintained as an isolated tool branch in DAG.

## Features
- Temperature-based PWM fan curve with configurable start and full-speed temperatures.
- Configurable polling interval.
- Optional `jetson_clocks` invocation at startup.
- systemd integration for automatic startup and restart-on-failure.
- A `uv`-managed Python project with tests, Ruff linting/formatting, and CI.

## Hardware and platform
This project targets a Jetson Nano 4 GB with a compatible 5 V PWM fan. It expects the following Linux interfaces, which must be verified on the target device:

- Temperature: `/sys/devices/virtual/thermal/thermal_zone0/temp`
- PWM target: `/sys/devices/pwm-fan/target_pwm`

The daemon needs root privileges to write the PWM sysfs node. Confirm the paths and hardware behavior on your image before installation, and ensure that the board and fan have an appropriate power supply.

## Quick start
Install `uv`, clone the DAG repository, and select this branch:

```bash
git clone https://github.com/MadhbhavikaR/DAG.git
cd DAG
git switch DAG-Jetson-Nano-4GB-Fan_Control
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

On the Jetson, after configuring the path in the system service or placing your JSON configuration at `/etc/jetson-fan-control/config.json`, run interactively with root privileges:

```bash
sudo uv run jetson-fan-control --config /etc/jetson-fan-control/config.json
```

Review [Installation](docs/installation.md) before enabling the service. Do not run an interactive controller alongside the system service; both would compete to write the PWM node.

## Configuration
The starter file is `config/config.json`. The service expects `/etc/jetson-fan-control/config.json`.

| Setting | Default | Meaning |
| --- | ---: | --- |
| `FAN_OFF_TEMP` | 20 | Temperature in °C at or below which the fan is off. |
| `FAN_MAX_TEMP` | 50 | Temperature in °C at or above which the fan runs at full speed. |
| `UPDATE_INTERVAL` | 2 | Polling interval in seconds. |
| `MAX_PERF` | 0 | When truthy, attempt to run `jetson_clocks` at startup. |

Speed is interpolated linearly between the temperature thresholds and clamped to PWM values 0–255. Thresholds are examples, not universal thermal recommendations; validate cooling under your actual enclosure, ambient temperature and workload.

## Documentation
- [Installation and systemd setup](docs/installation.md)
- [Configuration reference](docs/configuration.md)
- [Development and quality checks](docs/development.md)
- [Troubleshooting](docs/troubleshooting.md)

## Development
This project uses `uv` for environments/dependency management, pytest for tests, and Ruff for linting and formatting.

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## License
The migrated fan-control code retains its MIT license. See [LICENSE](LICENSE).
