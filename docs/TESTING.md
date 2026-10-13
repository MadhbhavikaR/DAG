# Testing and validation

From the repository root:

```sh
uv sync --locked --dev
uv run python -m py_compile src/__init__.py src/annas_archive.py src/config.py src/constants.py
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run python tools/build_plugin.py
uv run python tools/build_plugin.py --check
```

Tests run offline and should not require live mirrors, credentials, or the Calibre GUI. The build validates archive integrity and exact contents. Manually verify install, settings persistence, search results, mirror fallback, and link checks in a disposable Calibre profile when available; do not describe those checks as passing unless run.
