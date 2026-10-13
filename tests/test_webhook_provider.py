from unittest.mock import Mock

import requests

from notifier_service.models import Notification, WebhookConfig
from notifier_service.providers import WebhookProvider


def test_webhook_posts_json_and_returns_true() -> None:
    session = Mock(spec=requests.Session)
    response = Mock()
    session.post.return_value = response
    config = WebhookConfig(
        name="example",
        enabled=True,
        url="https://example.invalid/notify",
        headers={"Content-Type": "application/json"},
        payload={"message": "message"},
        format_message="text",
    )

    provider = WebhookProvider(config, session=session)

    assert provider.send(Notification("Hello *world*")) is True
    session.post.assert_called_once_with(
        "https://example.invalid/notify",
        json={"message": "Hello world"},
        data=None,
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    )
    response.raise_for_status.assert_called_once()


def test_webhook_returns_false_after_request_failure(monkeypatch) -> None:
    session = Mock(spec=requests.Session)
    session.post.side_effect = requests.Timeout("timed out")
    monkeypatch.setattr("notifier_service.providers.time.sleep", lambda _: None)
    monkeypatch.setattr("notifier_service.providers.random.uniform", lambda *_: 0)

    config = WebhookConfig(
        name="example",
        enabled=True,
        url="https://example.invalid/notify",
        max_attempts=2,
    )

    assert WebhookProvider(config, session=session).send(Notification("Hello")) is False
    assert session.post.call_count == 2


def test_disabled_webhook_skips_network() -> None:
    session = Mock(spec=requests.Session)
    config = WebhookConfig(name="disabled", enabled=False, url="")

    assert WebhookProvider(config, session=session).send(Notification("Hello")) is True
    session.post.assert_not_called()
