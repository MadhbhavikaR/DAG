"""Small typed models used by the notification framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Notification:
    """A notification before provider-specific formatting."""

    message: str
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("Notification message must not be empty")


@dataclass(frozen=True, slots=True)
class WebhookConfig:
    """Configuration for one generic HTTP notification destination."""

    name: str
    enabled: bool
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=lambda: {"message": "message"})
    format_message: str = "text"
    timeout_seconds: float = 15.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Webhook name must not be empty")
        if self.enabled and not self.url.startswith(("https://", "http://")):
            raise ValueError(f"Enabled webhook {self.name!r} must have an HTTP(S) URL")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")


@dataclass(frozen=True, slots=True)
class NotifierConfig:
    """Global settings and provider destinations for a notifier instance."""

    startup_message: bool = True
    minimum_repeat_minutes: int = 1
    webhooks: tuple[WebhookConfig, ...] = ()

    def __post_init__(self) -> None:
        if self.minimum_repeat_minutes < 1:
            raise ValueError("minimum_repeat_minutes must be at least 1")
        names = [webhook.name.casefold() for webhook in self.webhooks]
        if len(names) != len(set(names)):
            raise ValueError("Webhook destination names must be unique")
