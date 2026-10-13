# Installation and operations

## Development install

Install Python 3.10+ and [uv](https://docs.astral.sh/uv/), then from the repository root run:

```bash
uv sync --all-groups
```

Use `uv run` for commands to ensure they use the managed environment.

## Run the framework from Python

Create a configuration file following [Webhook configuration](config.md), then:

```python
from notifier_service import NotifierService
from notifier_service.config import load_config

service = NotifierService(load_config("config.json"))
if not service.notify("Hello from Notifier-Service"):
    raise SystemExit("At least one notification destination failed")
```

The current framework is a library-style core rather than a daemon with a built-in scheduling loop. A daemon, systemd service, or scheduled task can be added by an extension or application when needed.

## Deploying as a Linux service

Run the application through a dedicated virtual environment owned by the service account. Store configuration in a path readable only by that account. The example commands below are illustrative; change paths and user/group names to match your host.

```bash
sudo install -d -o notifier -g notifier /opt/notifier-service
sudo install -d -o notifier -g notifier /etc/notifier-service
```

Prepare the project environment as the `notifier` service user and configure systemd's `WorkingDirectory`, `ExecStart`, and `EnvironmentFile` for your actual deployment. Do not copy systemd unit files containing example or machine-specific paths without review.

## Fail2ban Telegram extension

See [the extension README](../extensions/fail2ban-telegram/README.md). The extension is a Fail2ban action module and must be installed where the Fail2ban service's Python interpreter can import its dependencies. Verify local action naming rules for your distribution/version.

## Troubleshooting

- Inspect application or Fail2ban logs for configuration validation and provider failures.
- Confirm URLs, credentials, headers, and payload schema for the receiving service.
- Ensure outbound HTTPS traffic is allowed by local firewall policy.
- The core retries network errors a bounded number of times; a successful HTTP response is considered delivered by the generic webhook provider.
