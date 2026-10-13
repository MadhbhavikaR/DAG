"""Core framework for configuration-driven multi-channel notifications."""

from notifier_service.core import NotifierService
from notifier_service.models import Notification, NotifierConfig
from notifier_service.providers import WebhookProvider

__all__ = ["Notification", "NotifierConfig", "NotifierService", "WebhookProvider"]
