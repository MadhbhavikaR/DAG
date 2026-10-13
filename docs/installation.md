# Installation and configuration

## Telegram setup

Create a Telegram bot with [BotFather](https://telegram.me/botfather), copy its API token, and send a message to the bot (or post in the group where it should notify). The bot must have permission to post to the destination chat.

Copy `telegram_config.json.example` to `telegram_config.json` in the configured Fail2ban action directory. Fill in:

- `telegram_api_token`: secret bot token; keep it out of version control.
- `telegram_chat_id`: numeric chat ID or channel/group identifier. Leaving it blank asks the action to inspect bot updates and persist the first usable chat ID.
- `receive_banned` and `receive_unbanned`: booleans that independently enable each event.

## Fail2ban setup

Copy `telegram.py` and the configured JSON file to the directory where Fail2ban loads action modules, commonly `/etc/fail2ban/action.d/`. By default, the script reads `/etc/fail2ban/action.d/telegram_config.json`; change `installpath` if needed.

Install `requests` into the Python environment used by the Fail2ban service. For development, use `uv sync --all-groups`. For system services, follow the distribution's Python packaging policy rather than assuming an interactive shell's virtual environment is available to the service.

Configure a jail in `jail.local`, for example:

```ini
[sshd]
enabled = true
action = telegram
maxretry = 5
findtime = 10m
bantime = 1h
```

Action names differ slightly between Fail2ban packaging/version conventions. Ensure your installation maps the `telegram` action name to this module.

Restart Fail2ban, then review the service log to confirm that the action loaded and message delivery is successful.

## Operational notes

- Requests use a finite timeout; network failures are logged instead of recursively retrying forever.
- IP country lookup is best-effort. A failure returns `Unknown` and does not block the notification.
- Telegram chat discovery needs at least one recent update visible to the bot. Explicitly setting `telegram_chat_id` is the most reliable deployment method.
- The action writes a discovered ID back into `telegram_config.json`; ensure the service has write permission if automatic discovery is enabled.
