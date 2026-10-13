"""Fail2ban action for sending ban and unban notifications to Telegram."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import requests
from fail2ban.server.actions import ActionBase

LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


class TelegramAction(ActionBase):
    """Send Fail2ban lifecycle and IP ban events to a Telegram chat."""

    def __init__(self, jail: Any, name: str) -> None:
        super().__init__(jail, name)
        self.installpath = Path("/etc/fail2ban/action.d")
        self.config_path = self.installpath / "telegram_config.json"
        self.config: dict[str, Any] = {}
        self.token = ""
        self.chat_id: str | int | None = None
        self._load_config()
        self.token = str(self.config.get("telegram_api_token", "")).strip()
        self.chat_id = self.config.get("telegram_chat_id") or None

        if not self.token:
            raise ValueError(f"Missing telegram_api_token in {self.config_path}")

        if not self.chat_id:
            self.get_chat_id()

    def _load_config(self) -> None:
        """Load and validate JSON configuration."""
        try:
            with self.config_path.open(encoding="utf-8") as config_file:
                config = json.load(config_file)
        except OSError as exc:
            raise RuntimeError(f"Unable to read Telegram config at {self.config_path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in Telegram config at {self.config_path}") from exc

        if not isinstance(config, dict):
            raise ValueError("Telegram configuration must be a JSON object")

        config.setdefault("telegram_api_token", "")
        config.setdefault("telegram_chat_id", "")
        config.setdefault("receive_banned", True)
        config.setdefault("receive_unbanned", True)
        self.config = config

    def _save_config(self) -> None:
        """Persist config without converting the JSON object into a string."""
        with self.config_path.open("w", encoding="utf-8") as config_file:
            json.dump(self.config, config_file, indent=2)
            config_file.write("\n")

    def get_chat_id(self) -> str | int | None:
        """Discover the latest chat ID from Telegram updates."""
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{self.token}/getUpdates",
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            updates = payload.get("result", [])
            for update in reversed(updates):
                message = update.get("message") or update.get("channel_post")
                chat = message.get("chat") if isinstance(message, dict) else None
                if isinstance(chat, dict) and chat.get("id") is not None:
                    self.chat_id = chat["id"]
                    self.config["telegram_chat_id"] = self.chat_id
                    self._save_config()
                    LOGGER.info("Telegram destination chat ID discovered")
                    return self.chat_id
        except (requests.RequestException, ValueError, KeyError, OSError) as exc:
            LOGGER.warning("Could not discover Telegram chat ID: %s", exc)

        LOGGER.warning(
            "Telegram chat ID is not configured. Set telegram_chat_id in %s.",
            self.config_path,
        )
        return None

    def send_message(self, message: str) -> bool:
        """Send a message, returning False when delivery cannot be completed."""
        if not self.chat_id:
            LOGGER.error("Cannot send Telegram notification: no chat ID is configured")
            return False

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json()
            if not result.get("ok", False):
                LOGGER.error("Telegram API rejected a notification")
                return False
        except (requests.RequestException, ValueError) as exc:
            LOGGER.error("Could not send Telegram notification: %s", exc)
            return False

        return True

    def start(self) -> None:
        """Notify Telegram that Fail2ban started."""
        self.send_message("Fail2ban started.")

    def stop(self) -> None:
        """Notify Telegram that Fail2ban stopped."""
        self.send_message("Fail2ban stopped.")

    def ban(self, aInfo: dict[str, Any]) -> None:  # noqa: N803 - Fail2ban API name
        """Handle Fail2ban's ban callback."""
        if self.config.get("receive_banned", True):
            ip_address = str(aInfo.get("ip", "Unknown"))
            location = self.get_location(ip_address)
            self.send_message(f"{ip_address} from {location} banned")

    def unban(self, aInfo: dict[str, Any]) -> None:  # noqa: N803 - Fail2ban API name
        """Handle Fail2ban's unban callback."""
        if self.config.get("receive_unbanned", True):
            ip_address = str(aInfo.get("ip", "Unknown"))
            location = self.get_location(ip_address)
            self.send_message(f"{ip_address} from {location} unbanned")

    @staticmethod
    def get_location(ip: str) -> str:
        """Return the country name for an IP, or Unknown when lookup fails."""
        try:
            response = requests.get(
                f"https://ipapi.co/{ip}/json/",
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            country = payload.get("country_name")
            return str(country) if country else "Unknown"
        except (requests.RequestException, ValueError) as exc:
            LOGGER.debug("IP country lookup failed for %s: %s", ip, exc)
            return "Unknown"


# Fail2ban loads this conventional module-level class name.
Action = TelegramAction
