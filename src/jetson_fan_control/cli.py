"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import subprocess
import time
from pathlib import Path

from jetson_fan_control.config import FanConfig
from jetson_fan_control.controller import (
    DEFAULT_PWM_PATH,
    DEFAULT_TEMP_PATH,
    FanController,
)

DEFAULT_CONFIG_PATH = Path("/etc/jetson-fan-control/config.json")
LOGGER = logging.getLogger("jetson_fan_control")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Control a Jetson Nano PWM fan from the board temperature."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"JSON config path (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument("--temperature-path", type=Path, default=DEFAULT_TEMP_PATH)
    parser.add_argument("--pwm-path", type=Path, default=DEFAULT_PWM_PATH)
    return parser


def main() -> int:
    """Run the fan-control loop until stopped."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = build_parser().parse_args()

    try:
        config = FanConfig.from_file(args.config)
        controller = FanController(
            config,
            temperature_path=args.temperature_path,
            pwm_path=args.pwm_path,
        )
        if config.max_perf:
            LOGGER.info("MAX_PERF enabled; attempting to run jetson_clocks")
            try:
                subprocess.run(["jetson_clocks"], check=True, timeout=30)
            except (OSError, subprocess.SubprocessError) as exc:
                LOGGER.warning("Could not run jetson_clocks: %s", exc)

        LOGGER.info(
            "Fan controller started (poll interval: %s seconds)",
            config.update_interval,
        )
        while True:
            temperature, speed, changed = controller.update()
            if changed:
                LOGGER.info(
                    "Temperature %.1f °C; PWM target %d/255",
                    temperature,
                    speed,
                )
            time.sleep(config.update_interval)
    except KeyboardInterrupt:
        LOGGER.info("Stopping fan controller.")
        return 0
    except (OSError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1
