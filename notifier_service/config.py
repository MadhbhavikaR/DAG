"""JSON configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from notifier_service.models import NotifierConfig, WebhookConfig

_RESERVED_KEYS = {"STARTUP_MESSAGE", "MIN_REPEAT", "DEFAULT_DOT_STYLE"}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def load_config(path: str | Path) -> NotifierConfig:
    """Load global settings and generic webhook definitions from JSON."""
    config_path = Path(path)
    try:
        data: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Unable to read notifier configuration: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in notifier configuration: {config_path}") from exc

    if not isinstance(data, dict):
        raise ValueError("Notifier configuration must be a JSON object")

    destinations: list[WebhookConfig] = []
    for name, destination in data.items():
        if name in _RESERVED_KEYS:
            continue
        if not isinstance(destination, dict):
            raise ValueError(f"Destination {name!r} must be a JSON object")

        enabled = bool(destination.get("ENABLED", False))
        raw_urls = destination.get("WEBHOOK_URL")
        if raw_urls is None:
            if enabled:
                raise ValueError(f"Enabled destination {name!r} requires WEBHOOK_URL")
            continue

        urls = _as_list(raw_urls)
        headers = _as_list(destination.get("HEADER", [{} for _ in urls]))
        payloads = _as_list(destination.get("PAYLOAD", [{"message": "message"} for _ in urls]))
        formats = _as_list(destination.get("FORMAT_MESSAGE", ["text"] * len(urls)))

        if not (len(urls) == len(headers) == len(payloads) == len(formats)):
            raise ValueError(
                f"Destination {name!r}: WEBHOOK_URL, HEADER, PAYLOAD, and "
                "FORMAT_MESSAGE must have the same number of entries"
            )

        for index, url in enumerate(urls):
            if not isinstance(url, str):
                raise ValueError(f"Destination {name!r} URL entries must be strings")
            header = headers[index] or {}
            payload = payloads[index]
            if not isinstance(header, dict) or not isinstance(payload, dict):
                raise ValueError(f"Destination {name!r} headers and payload must be objects")
            destinations.append(
                WebhookConfig(
                    name=f"{name}-{index + 1}" if len(urls) > 1 else name,
                    enabled=enabled,
                    url=url,
                    headers={str(key): str(value) for key, value in header.items()},
                    payload=payload,
                    format_message=str(formats[index]),
                )
            )

    try:
        repeat_minutes = max(int(data.get("MIN_REPEAT", 1)), 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("MIN_REPEAT must be an integer") from exc

    return NotifierConfig(
        startup_message=bool(data.get("STARTUP_MESSAGE", True)),
        minimum_repeat_minutes=repeat_minutes,
        webhooks=tuple(destinations),
    )
