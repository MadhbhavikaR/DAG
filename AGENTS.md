# DAG-Edit Development Contract

Read README.md and docs/README.md before changes. Runtime source lives in src/dag_edit/; edit.py remains a compatibility entry point.

- Preserve JSON protocol unless changes are documented and tested.
- Never guess stale or ambiguous hashes.
- Retain atomic mutation, stale-file checks, UTF-8 validation, newline handling, and permission preservation.
- Keep modules focused and imports acyclic.
- Add deterministic tests and update docs/schemas for protocol changes.
- Keep runtime dependencies standard-library-only unless justified.

Required checks: uv run ruff check src tests edit.py; uv run ruff format --check src tests edit.py; uv run pytest -q.
