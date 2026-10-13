# Notifier-Service DOX

## Purpose

- Define project-wide engineering contracts and index the DOX instruction hierarchy for Notifier-Service.
- Keep framework core, optional integrations, developer workflows, and project documentation understandable to maintainers and AI coding agents.
- DOX is documentation only: no runtime package, dependency, daemon, or code generator is required.

## Ownership

- The root owns project identity, package/dependency policy, repository-wide quality requirements, CI/release behavior, licensing boundaries, and the Child DOX Index.
- `README.md` owns the public-facing overview and quick start.
- `pyproject.toml` owns Python/project metadata, dependencies, and lint/test settings.
- `.github/workflows/` owns CI and tag-based GitHub Releases.
- `LICENSE` governs the existing MIT-licensed repository/framework; `LICENSE-GPL-3.0` and `docs/LICENSE-NOTICE.md` describe the GPL-3.0-or-later Fail2ban extension boundary.

## Local Contracts

- Keep the core package in `notifier_service/` independent of any one notification platform or host application.
- All platform-specific and host-specific integrations belong under `extensions/<name>/`; do not add an integration-specific dependency to the core unless it is required by a generic core feature.
- Provider extensions implement `NotificationProvider.send(notification) -> bool` from `notifier_service.providers` and are injected into `NotifierService`. Host-action extensions may expose host-specific entry points without pretending to be generic providers.
- Network calls must have finite timeouts and bounded retries. Tests must mock remote services and must never send messages to real destinations.
- Use `uv` for environment and dependency management. Keep dependency metadata and the lockfile in sync; CI should validate with `uv sync --locked --all-groups`.
- Required checks: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest`.
- Never commit access tokens, credentials, private webhook URLs, or live configuration files.
- Update the nearest owning `AGENTS.md` and all affected parent indexes when behavior, structure, contracts, workflows, or verification change. Follow the DOX chain before editing and run the applicable checks after meaningful changes.
- Release tags use `<branch-name>_<major>.<minor>.<patch>`, such as `Notifier-Service_0.1.0`; tag releases do not imply package publication.

## Work Guidance

- Prefer small, focused changes that preserve the public API and keep extensions replaceable.
- Document stable contracts and executable verification, not change diaries.
- Avoid adding a dependency just to support DOX; DOX consists of Markdown instructions.

## Verification

Run these commands from the repository root:

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Child DOX Index

| Child | Scope |
| --- | --- |
| `notifier_service/AGENTS.md` | Core notification models, configuration, formatting, providers, orchestration, and core tests. |
| `extensions/AGENTS.md` | Extension boundaries, discovery, authoring, licensing boundaries, and extension inventory. |
| `extensions/fail2ban-telegram/AGENTS.md` | Fail2ban action integration, Telegram settings, operations, and extension-specific verification. |
| `docs/AGENTS.md` | Architecture, configuration, installation, developer, release, and extension-authoring documentation. |
| `.github/AGENTS.md` | GitHub Actions CI, quality gates, tag validation, and release automation. |
