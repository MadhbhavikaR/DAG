# DAG Linux Telegram Notifications

Send Telegram notifications when Fail2ban starts or stops, or when an IP address is banned or unbanned. This utility is designed to be installed as a Fail2ban action on a Linux host.

## Features

- Sends start and stop notifications from Fail2ban.
- Sends ban and unban notifications, independently configurable.
- Adds a country name for an IP address when the IP lookup service is available.
- Uses a configurable Telegram bot token and chat ID.
- Isolated on its own DAG branch with dependency management through `uv`.

## Requirements

- Linux with Fail2ban installed.
- Python 3.10 or newer.
- A Telegram bot and the destination chat ID.
- `uv` for development and dependency management.

## Configure the Telegram bot

1. Create a bot in Telegram using [BotFather](https://telegram.me/botfather).
2. Copy the bot API token.
3. Start a conversation with the bot (or add it to the target group) and send a message so the bot can discover the chat.
4. Copy `telegram_config.json.example` to `telegram_config.json` and set `telegram_api_token` and `telegram_chat_id`.

Keep bot tokens private. Do not commit your real `telegram_config.json` or expose the token in logs.

## Install as a Fail2ban action

1. Copy `telegram.py` and your configured `telegram_config.json` to your Fail2ban action directory, usually `/etc/fail2ban/action.d/`.
2. Install the Python dependency in an environment accessible to the Python interpreter used by Fail2ban:

   ```bash
   uv sync --no-dev
   ```

   Ensure the runtime interpreter can import `requests`. If your distribution runs Fail2ban with its system Python, install project dependencies into a compatible environment according to your distribution's packaging policy.

3. In your Fail2ban jail configuration (for example, `/etc/fail2ban/jail.local`), select the action:

   ```ini
   [sshd]
   enabled = true
   action = telegram
   maxretry = 5
   findtime = 10m
   bantime = 1h
   ```

   Action names depend on your Fail2ban package and local action setup. Check your distribution's naming rules and use the action name mapped to this module.

4. Restart Fail2ban and inspect its service logs for configuration or delivery errors.

## Configuration

| Key | Type | Description |
| --- | --- | --- |
| `telegram_api_token` | string | Telegram bot API token. Required. |
| `telegram_chat_id` | string or number | Destination Telegram chat ID. Required for delivery. |
| `receive_banned` | boolean | Send notifications for bans. Defaults to `true`. |
| `receive_unbanned` | boolean | Send notifications for unbans. Defaults to `true`. |

See `telegram_config.json.example` for a template. The action reads configuration from the same directory as `telegram.py` by default; edit `installpath` in the action if your installation uses a different directory.

## Development

Install [uv](https://docs.astral.sh/uv/) and run:

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Auto-fix lint and formatting issues with `uv run ruff check --fix .` and `uv run ruff format .`.

## Releases

Create a tag whose name is `<branch-name>_<semantic-version>`. For this branch, an example is:

```bash
git tag DAG-Linux-Telegram-Notifications_0.1.0
git push origin DAG-Linux-Telegram-Notifications_0.1.0
```

The release workflow validates the tag format and creates a GitHub Release for the pushed tag. Release tags should point to the commit intended for release.

## Documentation

Additional setup notes and operational guidance live in `docs/`.

## License

The migrated Fail2ban action is licensed under GPL-3.0-or-later; see [LICENSE-GPL-3.0](LICENSE-GPL-3.0) and [the license notice](docs/LICENSE-NOTICE.md). DAG's repository-level license remains in [LICENSE](LICENSE).
