# Edit

Edit is a context-anchored, JSON-first command-line tool for creating, searching, reading, and mutating one UTF-8 text file at a time. Hashes returned by read/search anchor edits to the observed file version.

## Quick start

~~~bash
uv sync --all-groups
uv run edit --prompt
printf '%s' 'function_name' | uv run edit search path/to/file.py
~~~

The source-checkout entry point remains supported: `python edit.py --prompt`. Content and search queries come from stdin. JSON is the default output; use `--human` for readable output.

## Commands

- `create FILE`: create a new file from stdin.
- `rewrite FILE`: replace a whole file from stdin.
- `search FILE [--regex] [--limit N]`: search stdin text.
- `read FILE [HASH [BEFORE AFTER]]`: read a file or bounded context.
- `replace FILE HASH|START..END`: replace an inclusive range from stdin.
- `insert before|after FILE HASH`: insert stdin content at an anchor.
- `delete FILE HASH|START..END`: delete an inclusive range.
- `prompt`: print the compact agent protocol.

## Layout

~~~text
src/dag_edit/  Runtime package, separated by responsibility
tests/         CLI contract and filesystem safety tests
docs/          Protocol, operations, schemas, architecture
skill/edit/    Agent usage instructions
.github/       CI and release workflows
edit.py        Source-checkout compatibility entry point
~~~

## Development

~~~bash
uv sync --all-groups
uv run ruff check src tests edit.py
uv run pytest -q
uv run pytest --cov --cov-report=term-missing
~~~

Safety invariants include atomic replacement, stale-anchor checks, UTF-8 validation, newline handling, and structured JSON errors on stderr. The index cache is stored under the operating system's temporary directory.
