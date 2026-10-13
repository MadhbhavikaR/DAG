# Annas-Archieve-Calibre-Plugin

Browse Anna's Archive through Calibre's **Get Books** interface with this store plugin.

## Install

Download the plugin ZIP from the build workflow artifact or a release. In Calibre, open **Preferences → Plugins → Load plugin from file** and select the ZIP, then restart Calibre if prompted.

## Development

This is a Python project managed with [uv](https://docs.astral.sh/uv/). Install Git, Python 3.11 or later, and uv, then run:

```sh
uv sync --locked --dev
uv run python -m py_compile src/__init__.py src/annas_archive.py src/config.py src/constants.py
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run python tools/build_plugin.py
```

The Calibre runtime code is under `src/`. The build script places the contents of `src/` at the root of the installable ZIP, which is the layout Calibre expects. Generated ZIPs are build artifacts and should not be committed.

## Features

- Search with sorting, language, file-type, content, access, and source filters.
- Add, edit, delete, and reorder mirrors; the default mirror is `https://annas-archive.gd`.
- Optionally filter download links by URL extension or HTTP Content-Type.

Live-site behavior and mirror availability can change over time. Automated tests are offline; a successful test run does not guarantee current site compatibility.

This plugin is derived from [ScottBot10/calibre_annas_archive](https://github.com/ScottBot10/calibre_annas_archive).
