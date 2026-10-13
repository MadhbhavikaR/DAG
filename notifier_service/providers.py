"""Generic HTTP webhook delivery and provider interface."""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Protocol

import requests

from notifier_service.formatting import format_message
from notifier_service.models import Notification, WebhookConfig

LOGGER = logging.getLogger(__name__)


class NotificationProvider(Protocol):
    """Interface extensions may implement to deliver notifications."""

    def send(self, notification: Notification) -> bool:
        """Deliver a notification and return whether delivery succeeded."""


class WebhookProvider:
    """Send notifications to configurable HTTP endpoints with bounded retries."""

    def __init__(self, config: WebhookConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    @staticmethod
    def _make_payload(
        template: dict[str, Any], notification: Notification, formatted: str
    ) -> tuple[dict[str, Any] | None, bytes | None]:
        raw_body = "data" in template
        payload = dict(template)
        for key, value in tuple(payload.items()):
            if key in {"text", "content", "message", "body", "formatted_body", "data"}:
                payload[key] = formatted
            elif key == "title":
                payload[key] = notification.title or (formatted.splitlines()[0] if formatted else "")
            elif key == "extras" and isinstance(value, dict):
                extras = dict(value)
                extras["message"] = formatted
                payload[key] = extras
            elif isinstance(value, str):
                payload[key] = value.replace("{message}", formatted)

        if raw_body:
            return None, formatted.encode("utf-8")
        return payload, None

    def send(self, notification: Notification) -> bool:
        """Send a notification; network errors trigger bounded exponential backoff."""
        if not self.config.enabled:
            LOGGER.debug("Notification destination %s is disabled", self.config.name)
            return True

        formatted = format_message(notification.message, self.config.format_message)
        payload, data = self._make_payload(self.config.payload, notification, formatted)
        last_error: requests.RequestException | None = None

        for attempt in range(self.config.max_attempts):
            try:
                response = self.session.post(
                    self.config.url,
                    json=payload,
                    data=data,
                    headers=self.config.headers,
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                LOGGER.info("Delivered notification via %s", self.config.name)
                return True
            except requests.RequestException as exc:
                last_error = exc
                LOGGER.warning(
                    "Delivery via %s failed (%d/%d): %s",
                    self.config.name,
                    attempt + 1,
                    self.config.max_attempts,
                    exc,
                )
                if attempt + 1 < self.config.max_attempts:
                    delay = min(2**attempt + random.uniform(0, 1), 30)
                    time.sleep(delay)

        LOGGER.error("Delivery via %s failed after retries: %s", self.config.name, last_error)
        return False
