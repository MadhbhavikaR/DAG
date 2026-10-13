# Development

## Tooling

- Python 3.10 or newer
- `uv` for project and dependency management
- pytest for unit tests
- Ruff for linting and formatting
- GitHub Actions for automated quality checks

## Set up

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

To apply formatting and safe lint fixes locally:

```bash
uv run ruff check --fix .
uv run ruff format .
```

Run `uv lock` and commit `uv.lock` whenever you intend to pin the project's resolved dependencies for reproducible installs. This initial migration omits the generated lockfile so it can be created with the intended uv version.

## Layout

- `src/jetson_fan_control/config.py`: JSON parsing and validation
- `src/jetson_fan_control/controller.py`: sensor reads, fan curve, PWM writes
- `src/jetson_fan_control/cli.py`: CLI and polling lifecycle
- `tests/`: hardware-independent unit tests using temporary files
- `systemd/` and `scripts/`: deployment artifacts
- `docs/`: user and developer documentation

## Design notes

The fan-curve calculation is pure and tested separately from sysfs. Hardware paths can be overridden via CLI options for testability. Run a single instance so separate loops do not compete to update PWM. Hardware-specific behavior still needs on-device validation; CI only covers hardware-independent behavior.
