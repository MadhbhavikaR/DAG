from notifier_service.core import NotifierService
from notifier_service.models import Notification, NotifierConfig, WebhookConfig


class FakeProvider:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.received: list[Notification] = []

    def send(self, notification: Notification) -> bool:
        self.received.append(notification)
        return self.result


def test_notification_rejects_empty_message() -> None:
    try:
        Notification("  ")
    except ValueError as exc:
        assert "must not be empty" in str(exc)
    else:
        raise AssertionError("Empty messages should be rejected")


def test_notifier_dispatches_to_all_providers() -> None:
    first = FakeProvider()
    second = FakeProvider()
    service = NotifierService(NotifierConfig(startup_message=False), [first, second])

    assert service.notify("deploy complete", title="deploy") is True
    assert len(first.received) == 1
    assert len(second.received) == 1
    assert first.received[0].title == "deploy"


def test_notifier_returns_false_if_any_provider_fails() -> None:
    service = NotifierService(
        NotifierConfig(startup_message=False),
        [FakeProvider(True), FakeProvider(False)],
    )

    assert service.notify("message") is False


def test_startup_respects_configuration() -> None:
    service = NotifierService(NotifierConfig(startup_message=False), [])

    assert service.startup() is True


def test_disabled_webhook_is_valid_without_url() -> None:
    config = WebhookConfig(name="disabled", enabled=False, url="")

    assert config.enabled is False
