# Notifier-Service

Notifier-Service is a Python framework for sending application notifications to multiple messaging services and webhooks through a consistent API. The framework core owns notification models, configuration, formatting, and delivery orchestration. Platform- and domain-specific behavior lives in independent extensions under `extensions/`.

## Design

```text
application or extension
          |
          v
   NotifierService
          |
          +---- NotificationProvider protocol
          |
          +---- WebhookProvider (built in)
          |
          +---- extensions/<extension-name>/
```

The core remains independent of particular notification services. Extensions may implement the provider protocol and register with `NotifierService`, or expose an external integration such as a Fail2ban action.

## Included capabilities

- **Generic webhook delivery:** configurable URL, headers, JSON payload templates, and multiple destinations.
- **Message formatting:** plain text, HTML, Markdown, and simplified Markdown.
- **Bounded retry handling:** finite HTTP timeouts, retry limits, and exponential backoff.
- **Extension layout:** optional integrations live under `extensions/`.
- **Fail2ban Telegram extension:** sends Fail2ban lifecycle and ban/unban notifications to Telegram.
- **DOX project guidance:** scoped `AGENTS.md` files define engineering contracts and keep project context discoverable for AI coding agents. DOX adds no runtime dependency.

## Requirements

- Python 3.10 or newer.
- [uv](https://docs.astral.sh/uv/) for development and dependency management.
- Network access from the host to configured notification services.

## Getting started

Clone the repository and enter the project root:

```bash
git clone https://github.com/MadhbhavikaR/DAG.git
cd DAG
git checkout Notifier-Service
uv sync --all-groups
```

Create a configuration file such as `config.json` using this minimal webhook example:

```json
{
  "STARTUP_MESSAGE": true,
  "MIN_REPEAT": 1,
  "EXAMPLE_WEBHOOK": {
    "ENABLED": true,
    "WEBHOOK_URL": ["https://example.invalid/notify"],
    "HEADER": [{"Content-Type": "application/json"}],
    "PAYLOAD": [{"message": "message"}],
    "FORMAT_MESSAGE": ["text"]
  }
}
```

Replace the sample URL and payload with the receiving service's actual webhook endpoint and required payload schema. Do not store real credentials or private webhook URLs in version control.

A minimal application can load the configuration and send a notification:

```python
from notifier_service import NotifierService
from notifier_service.config import load_config

config = load_config("config.json")
service = NotifierService(config)
success = service.notify("Deployment completed", title="Deployment")
if not success:
    raise SystemExit("One or more notification providers failed")
```

The framework currently provides the reusable notification API, configuration loader, and generic webhook delivery. The scheduled DietPi update-check loop from the initial service reference is intentionally not part of the framework core; implement it as an independent extension or application if required.

## Fail2ban Telegram extension

The Fail2ban integration lives in `extensions/fail2ban-telegram/`. Read its [extension documentation](extensions/fail2ban-telegram/README.md) for installation and configuration. It preserves Fail2ban action callbacks while improving network timeouts, error handling, and configuration persistence.

## DOX guidance

This repository adopts [agent0ai/dox](https://github.com/agent0ai/dox), a lightweight `AGENTS.md` documentation convention. It is not a Python library or service dependency.

Start with [root AGENTS.md](AGENTS.md), then read the closest scoped contract before changing files: [core guidance](notifier_service/AGENTS.md), [extension guidance](extensions/AGENTS.md), [Fail2ban extension guidance](extensions/fail2ban-telegram/AGENTS.md), [documentation guidance](docs/AGENTS.md), and [automation guidance](.github/AGENTS.md). After a meaningful change, update the nearest owning guide and any affected indexes.

## Development and quality checks

Install the runtime and development dependency groups and run the quality checks:

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The same checks run in GitHub Actions for Python 3.10, 3.11, and 3.12. Tests should mock network access and must not post to real messaging endpoints.

## Documentation

- [Architecture](docs/architecture.md)
- [Webhook configuration](docs/config.md)
- [Installation and operations](docs/installation.md)
- [Development and release process](docs/development.md)
- [Extension authoring](docs/extension-authoring.md)
- [Extensions overview](extensions/README.md)
- [DOX project instructions](AGENTS.md)

## Releases

Push a tag with the format `<branch-name>_<major>.<minor>.<patch>`. For this branch:

```bash
git tag Notifier-Service_0.1.0
git push origin Notifier-Service_0.1.0
```

The GitHub Actions workflow validates the name and creates a GitHub Release with generated release notes.

## Licensing

The framework uses DAG's existing MIT license. The migrated Fail2ban Telegram extension retains its GPL-3.0-or-later licensing; see [LICENSE-GPL-3.0](LICENSE-GPL-3.0) and [the license notice](docs/LICENSE-NOTICE.md).
