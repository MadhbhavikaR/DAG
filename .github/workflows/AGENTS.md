# Workflow-specific contract

## Purpose
Describe workflows stored in this directory.

## Ownership
- `release.yml` handles tag-triggered releases.

## Local Contracts
A pushed `Kindle-Fetch_<major>.<minor>.<patch>` tag triggers packaging and release. The ZIP name includes the semantic version.

## Work Guidance
Keep action permissions minimal and tag validation explicit.

## Verification
Validate YAML and tag patterns after edits.

## Child DOX Index
No child DOX files currently.
