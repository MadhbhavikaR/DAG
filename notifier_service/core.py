"""Notification service orchestration."""

from __future__ import annotations

import logging
from collections.abc import Iterable

from notifier_service.models import Notification, NotifierConfig
from notifier_service.providers import NotificationProvider, WebhookProvider

LOGGER = logging.getLogger(__name__)


class NotifierService:
    """Framework core dispatching notifications to registered providers."""

    def __init__(
        self,
        config: NotifierConfig,
        providers: Iterable[NotificationProvider] | None = None,
    ) -> None:
        self.config = config
        if providers is None:
            providers = (WebhookProvider(webhook) for webhook in config.webhooks)
        self.providers = tuple(providers)

    def notify(
        self,
        message: str,
        *,
        title: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        """Send a message through all providers and return aggregate success."""
        notification = Notification(message=message, title=title, metadata=metadata or {})
        success = True
        for provider in self.providers:
            try:
                if not provider.send(notification):
                    success = False
            except Exception:
                LOGGER.exception(
                    "Notification provider %s raised an unexpected error",
                    type(provider).__name__,
                )
                success = False
        return success

    def startup(self) -> bool:
        """Optionally emit a framework startup message."""
        if not self.config.startup_message:
            return True
        return self.notify("Notifier-Service started.", title="Notifier-Service")

    def healthcheck(self) -> dict[str, object]:
        """Return a framework status snapshot without probing remote providers."""
        return {
            "provider_count": len(self.providers),
            "enabled_provider_count": sum(
                isinstance(provider, WebhookProvider) and provider.config.enabled
                for provider in self.providers
            ),
        }
