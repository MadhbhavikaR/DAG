#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

systemctl disable --now jetson-fan-control.service 2>/dev/null || true
rm -f /etc/systemd/system/jetson-fan-control.service
systemctl daemon-reload
rm -rf /opt/jetson-fan-control

echo "Service and application files removed."
echo "Configuration was retained at /etc/jetson-fan-control/config.json."
