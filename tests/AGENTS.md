# Tests Subtree Contract

This contract applies to everything under `tests/`.

## Local Rules

- Add or update tests for every behavior change.
- Prefer contract-level tests for protocol shapes to prevent regressions.
- Keep tests deterministic and isolated.
- Validate both success behavior and failure guidance where relevant.

## Verification Focus

- `uv run --system-certs pytest -q`