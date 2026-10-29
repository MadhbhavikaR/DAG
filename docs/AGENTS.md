# Docs Subtree Contract

This contract applies to everything under `docs/`.

## Local Rules

- Keep docs aligned with runtime behavior in the same change.
- Keep operational guidance command-accurate and state-aware.
- Keep schema/contract docs synchronized with test expectations.
- Write for fast scanning: summary first, constraints second, execution details third.

## Verification Focus

- Ensure all referenced local doc links resolve.
- Ensure command examples use `uv --system-certs` where applicable.