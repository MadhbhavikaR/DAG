# Configuration reference

Configuration is a UTF-8 JSON object. The sample file lives at `config/config.json`; the installed service reads `/etc/jetson-fan-control/config.json`.

| Key | Type | Default | Description |
| --- | --- | ---: | --- |
| `FAN_OFF_TEMP` | number | 20 | Temperature in °C at or below which PWM is zero. |
| `FAN_MAX_TEMP` | number | 50 | Temperature in °C at or above which PWM is 255. Must exceed `FAN_OFF_TEMP`. |
| `UPDATE_INTERVAL` | number | 2 | Seconds between sensor reads. Must be greater than zero. |
| `MAX_PERF` | boolean or number | 0 | If truthy, attempt `jetson_clocks` once during startup. |

The PWM output is linearly interpolated between the temperature limits and clamped to the inclusive range 0–255. The controller writes to the PWM sysfs node only when the requested speed changes.

Choose thresholds for the actual chassis, fan, ambient temperature and workload. These defaults are examples, not universal thermal recommendations. Validate temperatures under sustained load and monitor the board after any change. If `MAX_PERF` is enabled, ensure that `jetson_clocks` is installed and understand that maximum clocks can increase heat and power use.
