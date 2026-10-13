# Development

## Environment

Install Python 3.10+ and [uv](https://docs.astral.sh/uv/). Create the environment and install the runtime and development groups:

```bash
uv sync --all-groups
```

## Quality checks

Run the same checks used by continuous integration:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Format and automatically resolve supported lint findings with:

```bash
uv run ruff check --fix .
uv run ruff format .
```

Tests should mock network access; they should not make requests to Telegram or the IP location provider.

## Branch and release conventions

This utility's working branch is `DAG-Linux-Telegram-Notifications`. Create release tags using:

```text
<branch-name>_<major>.<minor>.<patch>
```

For example, `DAG-Linux-Telegram-Notifications_0.1.0`. Pushing a correctly formatted tag triggers the GitHub Release workflow.
