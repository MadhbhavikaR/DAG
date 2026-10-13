# GitHub Automation DOX

## Purpose
- Own repository CI automation, release trigger conventions, quality gates, and release creation.

## Ownership
- `workflows/ci.yml` owns Python matrix testing and style/lint checks.
- `workflows/release.yml` owns tag-name validation and GitHub Release creation.

## Local Contracts
- CI must install the project through `uv`, execute Ruff lint and formatting checks, and run pytest for supported Python versions.
- Release tags must match `<branch-name>_<semantic-version>`; `Notifier-Service_0.1.0` is the canonical example.
- The release workflow creates a GitHub Release with generated notes; it does not publish to package registries.

## Work Guidance
- Change branch/tag filters and tag validation together when release naming changes.
- Keep permissions least-privileged and avoid echoing secret values in logs.

## Verification
Review both workflow files against the documented commands and trigger conventions. For workflow changes, inspect the GitHub Actions result after push.

## Child DOX Index
No child DOX files.
