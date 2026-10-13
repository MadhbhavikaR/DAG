# Fail2ban Telegram Extension DOX

## Purpose
- Document the operational contract for the Fail2ban action that sends Telegram notifications for service lifecycle and ban/unban events.

## Ownership
- `telegram.py` owns action entry points and Telegram Bot API requests.
- `telegram_config.json.example` owns the safe configuration template.
- `README.md` owns installation, Fail2ban wiring, troubleshooting, and the extension license statement.
- `../../LICENSE-GPL-3.0` is the complete GPL-3.0-or-later license text applied to this extension.

## Local Contracts
- Keep Telegram credentials and chat IDs in a private deployment configuration; never commit a populated `telegram_config.json`.
- Maintain compatibility with Fail2ban's action callbacks (`start`, `stop`, `ban`, `unban`) and keep network requests bounded.
- Do not couple this host-action adapter to the generic core unless there is a concrete need; it is an extension boundary, not a core dependency.

## Work Guidance
- Update the example configuration and README together whenever configuration keys or action behavior change.
- Test message construction and failure handling without sending to Telegram.

## Verification
Run `uv run pytest tests/test_telegram.py` and the full `uv run pytest` suite.

## Child DOX Index
No child DOX files.
