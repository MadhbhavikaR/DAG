# Source Subtree Contract

This contract applies to everything under `src/`.

## Local Rules

- Preserve runtime protocol compatibility unless a contract change is intentional and documented.
- Keep command/error behavior deterministic and schema-aligned.
- Prefer small, composable functions and centralized helpers over duplicated branch logic.
- For Python classes, keep one class per file.
- Keep error payload construction centralized; avoid ad-hoc per-command response shapes for failures.
- Ensure user-facing failures consistently emit `error`, `what`, `do`, `hint`, and `gotcha`.
- Do not introduce stdin reads for commands that do not explicitly require stdin by contract.

## Verification Focus

- `uv run --system-certs ruff check src tests`
- `uv run --system-certs pytest -q`