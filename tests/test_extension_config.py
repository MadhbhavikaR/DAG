import json
from pathlib import Path


def test_fail2ban_extension_config_template() -> None:
    config_path = (
        Path(__file__).parents[1]
        / "extensions"
        / "fail2ban-telegram"
        / "telegram_config.json.example"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert config["telegram_api_token"] == ""
    assert config["telegram_chat_id"] == ""
    assert config["receive_banned"] is True
    assert config["receive_unbanned"] is True
