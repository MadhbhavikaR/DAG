# GitHub automation contract

## Purpose
Own branch-local automation and CI/CD.

## Ownership
- `workflows/release.yml` validates tags, packages the extension, and publishes a GitHub Release.

## Local Contracts
- Valid tags use `Kindle-Fetch_<major>.<minor>.<patch>`.
- Grant publishing only `contents: write`.
- Package only `kindlefetch/`; exclude runtime secrets and state.
- Use the GitHub-provided token.

## Work Guidance
Validate tags explicitly and fail closed on unsupported names.

## Verification
Check valid and invalid version examples and inspect the release ZIP.

## Child DOX Index
- `workflows/AGENTS.md` — workflow-specific responsibilities.
