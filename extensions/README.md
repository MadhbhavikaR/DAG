# Extensions

Extensions provide optional integrations or domain-specific behavior on top of the Notifier-Service core. Each extension belongs in its own directory under `extensions/` and should keep its code, configuration examples, tests, and installation documentation together.

## Extension contract

The framework exposes:

- `Notification`: an immutable message with an optional title and metadata.
- `NotificationProvider`: a protocol with `send(notification) -> bool`.
- `WebhookProvider`: configurable generic HTTP destination with bounded retries.
- `NotifierService`: orchestration across registered providers.

A provider extension can implement `NotificationProvider` and pass its instances to `NotifierService`. Keep the core independent of specific messaging platforms. Extensions should keep secrets out of checked-in configuration files, use finite timeouts, log delivery failures, and test network behavior with mocks.

## Current extension

- `fail2ban-telegram/`: Fail2ban action hooks for Telegram lifecycle, ban, and unban notifications.
