# Architecture

The utility is a Fail2ban action module. Fail2ban calls the module-level `Action` class using its action lifecycle and event hooks.

- `TelegramAction` loads the action configuration at initialization.
- `start` and `stop` send service lifecycle notifications.
- `ban` and `unban` conditionally send event notifications based on configuration.
- `get_location` performs a best-effort country lookup for the event IP.
- `send_message` sends a Telegram Bot API request using a finite timeout and reports delivery failures through Python logging.

External network failures are treated as operational errors rather than recursively retried. Sensitive bot credentials are supplied through a local configuration file and should never be committed.
