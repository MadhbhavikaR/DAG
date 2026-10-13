# Documentation DOX

## Purpose
- Own maintained documentation for architecture, configuration, installation, development, extension authoring, and licensing notices.

## Ownership
- `architecture.md`: core/extension boundary and delivery behavior.
- `config.md`: generic JSON configuration and payload conventions.
- `installation.md`: environment and deployment setup.
- `development.md`: developer workflow, quality checks, and release tags.
- `extension-authoring.md`: provider/host extension guidance.
- `LICENSE-NOTICE.md`: licensing boundaries for framework and migrated integration.
- `README.md` at repository root owns the public overview and documentation index.

## Local Contracts
- Keep examples consistent with the actual API and configuration parser.
- Call out clearly when a feature is optional or not implemented in core.
- Never include real credentials or private destination URLs in examples.
- Use links that resolve within this repository for local documentation.

## Work Guidance
- Update the architecture, relevant how-to page, and root README when a durable capability or configuration contract changes.
- Keep docs direct, task-oriented, and free of redundant historical notes.

## Verification
Review changed links and ensure example commands match `docs/development.md`; run project checks when documentation accompanies code changes.

## Child DOX Index
No child DOX files.
