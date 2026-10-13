# Runtime shell modules

## Purpose
Describe responsibilities and editing contracts for the modular shell runtime.

## Ownership
- `kindlefetch.sh`: startup, imports, menus, update checks, cleanup.
- `search.sh`: catalogue search, result parsing, pagination, source selection.
- `filters.sh`: interactive filters and saved parameters.
- `downloads/`: service-specific download flows.
- `local_books.sh`: browse and remove local items.
- `settings.sh`: preferences, mirror overrides, sign-in, update checks.
- `setup.sh`: initial configuration.
- `misc.sh`: persistence, JSON helpers, DNS, version, login, mirror probing.
- `update.sh`: update confirmation and installer invocation.
- `link_config`: encoded default mirror URLs.

## Local Contracts
- Modules are sourced by `kindlefetch.sh`; keep function and variable names consistent.
- Runtime state uses `/tmp`, `bin/kindlefetch_config`, and `bin/zlib_cookies.txt`.
- Treat remote catalogue responses as untrusted input.
- Never log or commit credentials and cookies.

## Work Guidance
Prefer small, module-scoped changes and preserve compatible function interfaces.

## Verification
Run shell syntax checks and test changed behavior with non-sensitive fixtures where possible.

## Child DOX Index
- `downloads/AGENTS.md` — download-specific contracts.
