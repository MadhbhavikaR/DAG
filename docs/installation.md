# Installation

## Before you begin

This controller is intended for an NVIDIA Jetson Nano 4 GB with a supported PWM fan. The implementation expects the thermal and PWM sysfs paths listed in the [README](../README.md). Confirm both paths exist on the target image and that the PWM node behaves as expected before installing a service.

The daemon writes to a hardware control node and must run as root. Review the scripts before executing them with elevated privileges.

## Install as a service

1. Install `uv` and ensure it is available to root when the service is started. See the official [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).
2. Check out the `DAG-Jetson-Nano-4GB-Fan_Control` branch and enter the project directory.
3. Review `config/config.json` and `systemd/jetson-fan-control.service`.
4. Run:

   ```bash
   sudo ./scripts/install.sh
   ```

The installer copies the application to `/opt/jetson-fan-control`, places the config under `/etc/jetson-fan-control/config.json`, installs the systemd unit and enables the service.

## Verify service status

```bash
sudo systemctl status jetson-fan-control.service
sudo journalctl -u jetson-fan-control.service -b
```

## Uninstall

```bash
sudo ./scripts/uninstall.sh
```

The uninstall script removes the unit and application files but keeps the configuration for later use.
