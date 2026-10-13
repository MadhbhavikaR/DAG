import json

from notifier_service.config import load_config


def test_load_config_reads_multiple_webhook_destinations(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "STARTUP_MESSAGE": False,
                "MIN_REPEAT": 4,
                "TELEGRAM": {
                    "ENABLED": True,
                    "WEBHOOK_URL": [
                        "https://example.invalid/one",
                        "https://example.invalid/two",
                    ],
                    "HEADER": [{"Content-Type": "application/json"}] * 2,
                    "PAYLOAD": [{"text": "message"}] * 2,
                    "FORMAT_MESSAGE": ["simplified", "html"],
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.startup_message is False
    assert config.minimum_repeat_minutes == 4
    assert [webhook.name for webhook in config.webhooks] == ["TELEGRAM-1", "TELEGRAM-2"]
    assert config.webhooks[1].format_message == "html"


def test_load_config_rejects_mismatched_endpoint_arrays(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "HOOK": {
                    "ENABLED": True,
                    "WEBHOOK_URL": ["https://example.invalid/one"],
                    "HEADER": [],
                    "PAYLOAD": [{"message": "message"}],
                    "FORMAT_MESSAGE": ["text"],
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        load_config(config_path)
    except ValueError as exc:
        assert "same number of entries" in str(exc)
    else:
        raise AssertionError("Mismatched endpoint arrays should be rejected")
