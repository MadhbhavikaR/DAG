# Kindle-Fetch — DOX project contract

## Purpose
Kindle-Fetch is the Kindle utility isolated on this branch of DAG. It provides a menu-driven shell interface for searching supported catalogues, downloading selected items to a Kindle, and managing local files and preferences.

## Ownership
- `kindlefetch/` owns the Kindle extension runtime, configuration, shell modules, and KUAL entry points.
- `install.sh` owns device-side installation and upgrades.
- `.github/workflows/` owns release automation for version tags.
- `docs/` owns contributor-facing design and operating documentation.
- `README.md` is the human-facing overview and usage guide; detailed project instructions belong in the DOX tree.

## Local Contracts
- Keep the extension installable as `extensions/kindlefetch/` with `config.xml`, `menu.json`, `run.sh`, and `bin/`.
- Preserve user configuration and service cookies across upgrades.
- Installer and in-app updater must fetch this branch.
- Release tags use `Kindle-Fetch_<major>.<minor>.<patch>` and package `kindlefetch/` as a ZIP.
- Do not commit user credentials, cookies, runtime config, generated archives, or version files.
- Keep the README human-oriented; contributor and implementation rules live here and under `docs/`.

## Work Guidance
- Prefer POSIX shell syntax in installer code; the extension runtime may use shell features required by the Kindle environment.
- Validate archive contents and tag shape before publishing a release.
- Keep source attribution limited to the single attribution line in `README.md`; retain upstream license obligations in `LICENSE`.

## Verification
- Run `sh -n install.sh` and suitable shell syntax checks over edited runtime scripts.
- Validate the workflow YAML and release-tag regexp.
- Confirm installer/updater URLs point to this repository and branch.
- Confirm the release archive contains the installable `kindlefetch/` directory.

## Child DOX Index
- `kindlefetch/AGENTS.md` — extension layout, startup contract, and runtime modules.
- `kindlefetch/bin/AGENTS.md` — runtime modules and interfaces.
- `kindlefetch/bin/downloads/AGENTS.md` — download module contracts.
- `docs/AGENTS.md` — documentation ownership and upkeep.
- `.github/AGENTS.md` — automation conventions.
- `.github/workflows/AGENTS.md` — workflow triggers and verification.
