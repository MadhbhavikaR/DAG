# Kindle extension contract

## Purpose
Define the runtime and packaging contract for `kindlefetch/`, installed under `extensions/kindlefetch/` on a jailbroken Kindle.

## Ownership
- `config.xml` defines extension metadata and KUAL integration.
- `menu.json` provides the launch item.
- `run.sh` starts the application through kterm.
- `bin/kindlefetch.sh` coordinates startup, configuration, menu navigation, and module imports.
- `bin/search.sh`, `bin/filters.sh`, `bin/downloads/`, `bin/local_books.sh`, `bin/settings.sh`, `bin/setup.sh`, `bin/misc.sh`, and `bin/update.sh` own runtime functions.

## Local Contracts
- Keep `config.xml`, `menu.json`, `run.sh`, and `bin/` at the installed extension root.
- Runtime paths assume `/mnt/us/extensions/kindlefetch` and use `/mnt/us` as the user storage root.
- `bin/link_config` is base64-encoded shell configuration loaded by `bin/misc.sh`; preserve its expected variable names.
- In-app update checks and installation must target this repository's `Kindle-Fetch` branch.
- Never commit credentials or generated settings.

## Work Guidance
Test shell syntax after module edits. Keep prompts actionable and do not print credentials.

## Verification
Check edited shell syntax, KUAL paths, and updater URLs.

## Child DOX Index
- `bin/AGENTS.md` — module responsibilities and interfaces.
