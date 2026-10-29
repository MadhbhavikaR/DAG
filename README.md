# DAG Template Python

A reusable Python project template using [uv](https://docs.astral.sh/uv/) for dependency and environment management, Ruff for formatting and linting, mypy for static type checking, and pytest for testing.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Git

## Get started

```bash
git clone https://github.com/MadhbhavikaR/DAG.git
cd DAG
git switch DAG-Template-Python
uv sync --all-groups
uv run python -m dag_template_python.cli
```

The template branch is named `DAG-Template-Python`. When using this repository as a starting point for a new project, rename the project in `pyproject.toml`, update the package directory under `src/`, and update the wheel package configuration and tests accordingly.

## Project layout

```text
.
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci.yml
│       └── release.yml
├── src/
│   └── dag_template_python/
│       ├── __init__.py
│       └── cli.py
├── tests/
│   └── test_cli.py
├── .python-version
├── pyproject.toml
└── README.md
```

## Development commands

```bash
uv sync --all-groups
uv run python -m dag_template_python.cli
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run ruff check --fix .
uv run mypy
uv run pytest --cov --cov-report=term-missing
```

CI runs formatting checks, linting, strict mypy checks, and tests with coverage on pushes and pull requests. Keep `uv.lock` committed for applications so local and CI dependency resolution stays reproducible; generate it with `uv lock` and commit it alongside dependency changes.

## Releases

Pushing a tag matching `DAG-Template-Python_X.Y.Z` automatically creates a GitHub Release with generated release notes. The workflow accepts stable semantic versions only: three numeric components, no leading zeroes except for zero itself, and no `v` prefix.

```bash
git switch DAG-Template-Python
git pull --ff-only
uv run pytest
git tag -a DAG-Template-Python_1.0.0 -m "Release 1.0.0"
git push origin DAG-Template-Python_1.0.0
```

The tag must point to the commit you want to release. The workflow validates the tag and uses GitHub's CLI to publish the release. The workflow requires the repository Actions token to have contents write permission.

## Quality principles

- Keep application code in `src/` so tests exercise the installed package layout.
- Declare runtime dependencies in `[project].dependencies` and developer tools in `[dependency-groups].dev`.
- Commit `uv.lock` for reproducible application environments.
- Add tests for new behavior and keep meaningful coverage.
- Keep type annotations explicit and run formatting, linting, and type checks before pushing.
- Never commit secrets; use GitHub Actions secrets for credentials.
