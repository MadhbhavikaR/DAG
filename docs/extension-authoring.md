# Extension authoring

Notifier-Service keeps channel integrations separate from its framework core. Each extension lives under `extensions/<name>/` and should contain its implementation, configuration example, tests, and local setup documentation.

## Provider extensions

Implement the protocol exposed by `notifier_service.providers.NotificationProvider`:

```python
from notifier_service.models import Notification


class ExampleProvider:
    def send(self, notification: Notification) -> bool:
        # Deliver through your provider SDK or API.
        # Return True only when the provider accepts the message.
        return True
```

Register an instance when constructing the service:

```python
from notifier_service import NotifierService, NotifierConfig

service = NotifierService(NotifierConfig(), providers=[ExampleProvider()])
success = service.notify("Example notification")
```

Provider adapters should validate their settings at startup, avoid logging credentials, use bounded timeouts and retries, and return failure when delivery cannot be confirmed.

## Host/application extensions

An extension may integrate with a host system such as Fail2ban without being a generic webhook provider. Keep host callbacks and host installation instructions in the extension directory, and avoid adding host-specific dependencies to the core.

## Testing

Mock network calls and provider SDK interactions. Add coverage for successful delivery, request failures, timeouts, disabled behavior, malformed configuration, and any provider-specific message transformations.
