# Core Package DOX

## Purpose
- Own the framework's reusable notification runtime, data models, configuration loading, message formatting, provider interface, and dispatch orchestration.

## Ownership
- `models.py`: notification/configuration data structures.
- `config.py`: generic JSON configuration parsing and validation.
- `formatting.py`: supported text formatting.
- `providers.py`: `NotificationProvider` contract and generic HTTP webhook implementation.
- `core.py`: provider registration, dispatch, aggregate result, startup message, and health snapshot.
- `../tests/`: core behavior and contracts are verified by the test suite; test ownership is indexed in the root and extension-specific docs.

## Local Contracts
- Keep this package platform-agnostic. Integration-specific APIs and host callbacks belong under `extensions/`.
- Providers return a boolean success result; unexpected provider exceptions are logged and counted as failures by `NotifierService`.
- HTTP delivery uses finite timeouts and bounded retry counts. Preserve deterministic testability by mocking network calls.
- Do not log secret values or include credentials in exceptions intended for users.

## Work Guidance
- Add a core abstraction only when it is useful to multiple integrations or part of the stable public API.
- Preserve the provider protocol and public constructor behavior unless all affected callers, documentation, and tests are updated.

## Verification
Run `uv run pytest`, `uv run ruff check notifier_service`, and `uv run ruff format --check notifier_service`.

## Child DOX Index
No child DOX files.
