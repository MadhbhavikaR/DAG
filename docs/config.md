# Webhook configuration

Notifier-Service reads a JSON object. Global settings and each destination are shown below.

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

## Global settings

| Setting | Default | Description |
| --- | --- | --- |
| `STARTUP_MESSAGE` | `true` | Whether `NotifierService.startup()` emits the framework startup message. |
| `MIN_REPEAT` | `1` | Minimum polling interval in minutes for extensions that poll. The core does not start a polling loop itself. |
| `DEFAULT_DOT_STYLE` | `true` | Retained for possible update-monitor extensions; the core does not render status dots. |

## Per-destination settings

| Setting | Required | Description |
| --- | --- | --- |
| `ENABLED` | No | Enable this destination; defaults to `false`. |
| `WEBHOOK_URL` | Yes when enabled | URL or array of destination URLs. Each URL must use HTTP or HTTPS. |
| `HEADER` | Yes | HTTP header object or array matching the URL count. |
| `PAYLOAD` | Yes | JSON payload template or array matching the URL count. |
| `FORMAT_MESSAGE` | Yes | `text`, `html`, `markdown`, or `simplified`; one value per URL. |

For multiple endpoints, `WEBHOOK_URL`, `HEADER`, `PAYLOAD`, and `FORMAT_MESSAGE` must each contain the same number of items. The loader creates a separate provider configuration for every endpoint.

## Payload templates

The provider replaces common message fields (`text`, `content`, `message`, `body`, and `formatted_body`) with the formatted notification. A `title` field receives the notification title (or the first message line). String values containing `{message}` also receive the formatted message.

For services such as Ntfy that accept a raw body, use a payload with a `data` field. The provider sends the formatted message as request-body bytes instead of JSON. Check each service's current API documentation for its accepted headers and payload schema.

## Security

Do not commit bot tokens, authorization headers, private webhook URLs, or account identifiers. Use a local ignored configuration file or your deployment's secret store. Treat webhook URLs as credentials when their possession grants access to a channel.
