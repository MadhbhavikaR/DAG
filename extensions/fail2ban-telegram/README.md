# Fail2ban Telegram extension

This extension provides Fail2ban action hooks that deliver lifecycle, ban, and unban notifications through the Telegram Bot API.

## Configuration

Copy `telegram_config.json.example` to `telegram_config.json` in the Fail2ban action directory (typically `/etc/fail2ban/action.d/`). Set `telegram_api_token` and `telegram_chat_id`. Keep the real configuration private; the repository ignores `telegram_config.json`.

- `receive_banned`: send notifications when an IP is banned.
- `receive_unbanned`: send notifications when an IP is unbanned.

## Installation

Copy `telegram.py` and the configured JSON file into the action directory used by your Fail2ban installation. Install the `requests` dependency in the Python environment used by the Fail2ban service. Add the action name to a jail's configuration according to your distribution's Fail2ban action naming rules.

For example, the jail configuration may include:

```ini
[sshd]
enabled = true
action = telegram
```

Restart Fail2ban and inspect its logs. HTTP requests have finite timeouts; failed delivery returns an error result rather than retrying indefinitely.

This extension retains GPL-3.0-or-later licensing. See [the extension license](../../LICENSE-GPL-3.0).
