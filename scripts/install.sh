#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo bash "$0" "$@"
fi

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/jetson-fan-control"
CONFIG_DIR="/etc/jetson-fan-control"
SERVICE_FILE="/etc/systemd/system/jetson-fan-control.service"

command -v uv >/dev/null 2>&1 || {
  echo "uv is required. Install uv first, then rerun this script." >&2
  exit 1
}

install -d "$INSTALL_DIR" "$CONFIG_DIR"
cp -R "$PROJECT_DIR/src" "$INSTALL_DIR/"
cp "$PROJECT_DIR/pyproject.toml" "$INSTALL_DIR/"
cp "$PROJECT_DIR/README.md" "$INSTALL_DIR/"
install -m 0644 "$PROJECT_DIR/LICENSE" "$INSTALL_DIR/LICENSE"
install -m 0644 "$PROJECT_DIR/config/config.json" "$CONFIG_DIR/config.json"
install -m 0644 "$PROJECT_DIR/systemd/jetson-fan-control.service" "$SERVICE_FILE"

cd "$INSTALL_DIR"
uv sync --no-dev
systemctl daemon-reload
systemctl enable --now jetson-fan-control.service

echo "Installed and started jetson-fan-control.service."
echo "Configure: $CONFIG_DIR/config.json"
