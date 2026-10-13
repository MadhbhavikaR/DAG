# Architecture

## Runtime
The extension installs to `/mnt/us/extensions/kindlefetch/` and is launched through KUAL using `config.xml` and `menu.json`. `run.sh` starts the main shell program in kterm.

`bin/kindlefetch.sh` initializes paths and state, sources feature modules, checks for updates, loads or creates configuration, probes mirrors, writes settings, and starts the main menu.

## Modules
| Path | Responsibility |
|---|---|
| `bin/search.sh` | Search, result parsing, pagination, and source selection |
| `bin/filters.sh` | Filter menu and saved filter parameters |
| `bin/downloads/lgli_download.sh` | Library Genesis download flow |
| `bin/downloads/zlib_download.sh` | Z-Library download flow and cookie handling |
| `bin/local_books.sh` | Browse and delete local files and directories |
| `bin/settings.sh` | Settings, mirror overrides, optional sign-in, and update checks |
| `bin/setup.sh` | First-run configuration |
| `bin/misc.sh` | Persistence, helpers, DNS changes, login, mirror probing |
| `bin/update.sh` | User-confirmed updates |

## Persistent state
- `bin/kindlefetch_config`: user preferences and service URLs.
- `bin/zlib_cookies.txt`: service session cookie jar.
- `bin/.version`: installed source revision.
- `/tmp`: transient search and filter state.

The installer attempts to preserve configuration and cookies during upgrades. Runtime state is excluded from version control.

## External dependencies
The Kindle needs a shell, `curl`, `unzip`, `base64`, standard text utilities, and kterm. Catalogues and mirrors are remote services and may change independently.
