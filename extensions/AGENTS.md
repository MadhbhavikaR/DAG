# Extensions DOX

## Purpose
- Own optional notification-provider and host/application integrations.

## Ownership
- Each integration has its own direct child directory and local README/AGENTS contract.
- `README.md` in this directory indexes shipped extensions and states the extension contract.
- The framework provider protocol is owned by `../notifier_service/providers.py`; generic dispatch is owned by `../notifier_service/core.py`.

## Local Contracts
- Keep each integration isolated under `extensions/<extension-name>/`.
- Provider integrations may implement `NotificationProvider.send(notification) -> bool`; host integrations may instead expose the entry point expected by their host.
- Keep integration-only dependencies, host-specific configuration, and operational instructions within the extension boundary.
- Supply examples, never live credentials. Use bounded network operations and test with mocks.
- Preserve each extension's documented license; do not assume the framework license overrides extension-specific licensing.

## Work Guidance
- Every new extension should include installation/configuration instructions and tests covering success and representative failure cases.
- Update this index and the root Child DOX Index when adding, removing, or renaming an extension.

## Verification
Run `uv run pytest` and review each extension's setup instructions against its current files.

## Child DOX Index
| Child | Scope |
| --- | --- |
| `fail2ban-telegram/AGENTS.md` | Fail2ban callbacks, Telegram delivery, configuration, installation, and verification. |
