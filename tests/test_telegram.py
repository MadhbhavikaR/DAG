import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import requests

MODULE_PATH = Path(__file__).parents[1] / "telegram.py"
SPEC = importlib.util.spec_from_file_location("telegram_action", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
telegram = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telegram)


def build_action(tmp_path: Path) -> telegram.TelegramAction:
    config_path = tmp_path / "telegram_config.json"
    config_path.write_text(
        json.dumps(
            {
                "telegram_api_token": "test-token",
                "telegram_chat_id": 12345,
                "receive_banned": True,
                "receive_unbanned": True,
            }
        ),
        encoding="utf-8",
    )
    action = telegram.TelegramAction.__new__(telegram.TelegramAction)
    action.installpath = tmp_path
    action.config_path = config_path
    action.config = {}
    action.token = ""
    action.chat_id = None
    action._load_config()
    action.token = action.config["telegram_api_token"]
    action.chat_id = action.config["telegram_chat_id"]
    return action


def test_load_config_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "telegram_config.json"
    path.write_text("{", encoding="utf-8")
    action = telegram.TelegramAction.__new__(telegram.TelegramAction)
    action.config_path = path

    try:
        action._load_config()
    except ValueError as exc:
        assert "Invalid JSON" in str(exc)
    else:
        raise AssertionError("Invalid JSON should be rejected")


def test_send_message_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    action = build_action(tmp_path)
    response = Mock()
    response.json.return_value = {"ok": True}
    monkeypatch.setattr(telegram.requests, "post", Mock(return_value=response))

    assert action.send_message("hello") is True
    telegram.requests.post.assert_called_once_with(
        "https://api.telegram.org/bottest-token/sendMessage",
        json={"chat_id": 12345, "text": "hello"},
        timeout=telegram.REQUEST_TIMEOUT_SECONDS,
    )


def test_send_message_returns_false_on_request_error(monkeypatch, tmp_path: Path) -> None:
    action = build_action(tmp_path)
    monkeypatch.setattr(
        telegram.requests,
        "post",
        Mock(side_effect=requests.Timeout("timeout")),
    )

    assert action.send_message("hello") is False


def test_country_lookup_returns_unknown_on_error(monkeypatch) -> None:
    monkeypatch.setattr(
        telegram.requests,
        "get",
        Mock(side_effect=requests.ConnectionError("offline")),
    )

    assert telegram.TelegramAction.get_location("192.0.2.1") == "Unknown"


def test_get_chat_id_persists_json_object(monkeypatch, tmp_path: Path) -> None:
    action = build_action(tmp_path)
    action.chat_id = None
    action.config["telegram_chat_id"] = ""
    response = Mock()
    response.json.return_value = {
        "ok": True,
        "result": [{"message": {"chat": {"id": 9876}}}],
    }
    monkeypatch.setattr(telegram.requests, "get", Mock(return_value=response))

    assert action.get_chat_id() == 9876
    saved = json.loads(action.config_path.read_text(encoding="utf-8"))
    assert saved["telegram_chat_id"] == 9876
    assert isinstance(saved, dict)


def test_ban_respects_receive_banned_flag(tmp_path: Path) -> None:
    action = build_action(tmp_path)
    action.config["receive_banned"] = False
    action.get_location = Mock(return_value="Exampleland")
    action.send_message = Mock()

    action.ban({"ip": "192.0.2.1"})

    action.get_location.assert_not_called()
    action.send_message.assert_not_called()


def test_unban_sends_notification_when_enabled(tmp_path: Path) -> None:
    action = build_action(tmp_path)
    action.get_location = Mock(return_value="Exampleland")
    action.send_message = Mock()

    action.unban({"ip": "192.0.2.2"})

    action.get_location.assert_called_once_with("192.0.2.2")
    action.send_message.assert_called_once_with("192.0.2.2 from Exampleland unbanned")
