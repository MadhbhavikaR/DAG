# Architecture

Notifier-Service separates reusable notification infrastructure from optional integrations and uses DOX (`AGENTS.md` files) to document engineering boundaries without adding runtime dependencies.

## Core package: `notifier_service/`

- `models.py` contains notification and configuration dataclasses.
- `config.py` loads and validates generic webhook configuration from JSON.
- `formatting.py` formats messages into supported text conventions.
- `providers.py` defines the provider protocol and generic HTTP webhook delivery.
- `core.py` orchestrates notifications across registered providers.

## Extension package: `extensions/`

Extensions contain platform-specific or application-specific behavior. An extension may implement `NotificationProvider` and pass it to `NotifierService(config, providers=[...])`. Alternatively, an extension can be an adapter consumed by another host application, as the Fail2ban action is.

## DOX documentation boundary

The root `AGENTS.md` owns repository-wide contracts and indexes scoped instruction files. Child `AGENTS.md` files define local ownership, behavior contracts, work guidance, verification, and child indexes. Before editing, follow the root-to-target chain. After meaningful changes, refresh the affected owner docs and indexes.

DOX is deliberately documentation-only in this project: there is no imported DOX module, CLI, daemon, or dependency. It supports the development workflow rather than participating in notification delivery.

## Delivery behavior

The generic webhook provider uses a finite timeout and a bounded number of attempts, with exponential backoff between failed attempts. The service returns aggregate success: every registered provider must report success for `notify` to return `True`. Disabled configured webhooks are treated as skipped/successful.

## Configuration

The configuration loader supports the existing `ENABLED`, `WEBHOOK_URL`, `HEADER`, `PAYLOAD`, and `FORMAT_MESSAGE` structure for generic destinations. It supports multiple endpoints per destination when matching-length arrays are supplied. Secrets should be supplied through deployment-specific files or secret management and never committed.
