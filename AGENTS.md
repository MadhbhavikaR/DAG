# Project contract

This branch contains Annas-Archieve-Callibre-Plugin, a Calibre Store plugin maintained as a branch-isolated utility within DAG.

- Runtime plugin files are under `src/`; installable ZIPs must contain the contents of `src/` at their root.
- Use `uv` for dependency and tooling management; keep `uv.lock` synchronized with `pyproject.toml`.
- Keep offline tests deterministic and do not claim Calibre GUI or live-site checks unless performed.
- Do not retain references to unrelated repositories or their authors. The sole source attribution is the required line in `README.md`.
- Do not commit generated ZIP archives.
- Update tests, packaging, workflows, and docs together when layout or versioning changes.
