# Configuration

The foundation uses a deliberately small UTF-8 \`KEY=VALUE\` file. It is not a general-purpose configuration language. Unknown keys, duplicate keys, malformed lines, empty values and invalid ranges are rejected.

## Precedence

1. Built-in defaults.
2. Selected config file.
3. Environment variables prefixed with \`DAG_\`.

## Supported file keys

| Key | Default | Validation |
|---|---|---|
| \`NVR_HOST\` | \`127.0.0.1\` | Non-empty hostname/IP without whitespace |
| \`NVR_HTTP_PORT\` | \`80\` | 1–65535 |
| \`NVR_RTSP_PORT\` | \`554\` | 1–65535 |
| \`NVR_CHANNELS\` | \`13\` | 1–16 |
| \`EVENT_QUEUE_CAPACITY\` | \`128\` | 1–4096 |
| \`MAX_CONCURRENT_INFERENCE\` | \`1\` | 1–2 |
| \`LOG_LEVEL\` | \`info\` | error, warn, info, debug |
| \`DATA_DIR\` | \`runtime\` | Non-empty path |

The inference concurrency limit is intentionally conservative for Jetson Nano 4GB. Raising it does not guarantee that the hardware can sustain it; future inference features must measure and enforce resource budgets.

## Environment overrides

Prefix file keys with \`DAG_\`, for example:

\`\`\`bash
export DAG_NVR_HOST=192.168.100.103
export DAG_NVR_CHANNELS=13
export DAG_LOG_LEVEL=debug
\`\`\`

## Example

Copy \`config/dag-nvr-ai.example.conf\` to \`config/dag-nvr-ai.local.conf\`. The local filename is ignored by Git. Do not put passwords, usernames, Telegram tokens or other secrets in the config file.

## Scope

This is the foundation configuration only. Camera mapping, zones, retention, notification and model settings will be added with their corresponding features and documented with validation rules.
