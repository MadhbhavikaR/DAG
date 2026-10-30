# Edit Development Contract

Read README.md and docs/README.md before changes. Runtime source lives in `src/edit/`; `edit.py` remains a source-checkout compatibility entry point.

- Preserve the JSON protocol unless changes are documented and tested.
- Never guess stale or ambiguous hashes.
- Retain atomic mutation, stale-file checks, UTF-8 validation, newline handling, and permission preservation.
- Keep modules cohesive, dependencies explicit, and imports acyclic.
- Prefer constructor injection over hidden global dependencies.
- Add deterministic tests and update docs/schemas for protocol changes.
- Keep runtime dependencies standard-library-only unless justified.

Required checks: `uv run ruff check src tests edit.py`; `uv run pytest -q`; `uv run pytest --cov --cov-report=term-missing`.
