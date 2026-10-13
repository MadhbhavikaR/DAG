# Troubleshooting

## Service fails to start

```bash
sudo systemctl status jetson-fan-control.service
sudo journalctl -u jetson-fan-control.service -b --no-pager
```

Check that the config file exists, contains valid JSON and uses a maximum temperature greater than the off temperature. Verify that uv and the installed entry point exist at the configured path.

## Temperature sensor cannot be read

Confirm that `/sys/devices/virtual/thermal/thermal_zone0/temp` exists and is readable. Its value is expected to be millidegrees Celsius (for example, `42000` means 42 °C). Kernel/device images may expose a different thermal-zone layout.

## Fan PWM cannot be written

Confirm `/sys/devices/pwm-fan/target_pwm` exists and that your device supports the expected PWM interface. The service runs as root, but a missing device node or unsupported hardware cannot be corrected by changing Python configuration alone.

## Fan remains off or runs at full speed

Review the two temperature thresholds and compare them with the reported sensor temperature. The fan curve is zero at or below `FAN_OFF_TEMP`, full at or above `FAN_MAX_TEMP`, and linear between them. Do not lower cooling capacity without validating temperatures during representative sustained workloads.

## `jetson_clocks` fails

Set `MAX_PERF` to `0` to disable the optional command. When enabled, failure to find or execute `jetson_clocks` is logged as a warning and does not stop the fan-control loop.
