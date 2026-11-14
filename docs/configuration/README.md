# Configuration

The application uses a deliberately small UTF-8 KEY=VALUE file for application settings. It is not a general-purpose configuration language. Unknown keys, duplicate keys, malformed lines, empty values and invalid ranges are rejected.

## Precedence

1. Built-in defaults.
2. Selected application config file.
3. Environment variables prefixed with DAG_.

## Supported application file keys

| Key | Default | Validation |
|---|---|---|
| NVR_HOST | 127.0.0.1 | Hostname, IPv4 or bracketed IPv6 |
| NVR_HTTP_PORT | 80 | 1–65535 |
| NVR_RTSP_PORT | 554 | 1–65535 |
| NVR_CHANNELS | 13 | 1–16 |
| CURL_BIN | curl | Executable name or path |
| EVENT_QUEUE_CAPACITY | 128 | 1–4096 |
| MAX_CONCURRENT_INFERENCE | 1 | 1–2 |
| LOG_LEVEL | info | error, warn, info, debug |
| DATA_DIR | runtime | Non-empty path |

The inference concurrency limit is intentionally conservative for Jetson Nano 4GB. Raising it does not guarantee that the hardware can sustain it; future inference features must measure and enforce resource budgets.

## Camera channel map

The optional camera map is a separate file with one mapping per line:

```text
1=front_gate
2=driveway
3=parking_area
```

Blank lines and lines beginning with # are ignored. Channel IDs must be unique and within the configured NVR_CHANNELS range. Labels must be 1–48 ASCII letters, digits, hyphens or underscores. Unmapped channels use generic labels such as channel-04.

These labels are operator-supplied metadata. Do not assume a channel corresponds to a specific physical camera until verified on the NVR. The map does not contain stream credentials.

## Environment overrides

Prefix application keys with DAG_, for example:

```bash
export DAG_NVR_HOST=192.168.100.103
export DAG_NVR_CHANNELS=13
export DAG_CURL_BIN=/usr/bin/curl
export DAG_LOG_LEVEL=debug
```

NVR credentials are supplied separately through DAG_NVR_USERNAME and DAG_NVR_PASSWORD. They are not part of either tracked configuration file and must never be committed.

## Example files

Copy config/dag-nvr-ai.example.conf to config/dag-nvr-ai.local.conf and config/cameras.example.conf to config/cameras.local.conf. Local filenames are ignored by Git. Do not put passwords, usernames, Telegram tokens or other secrets in config files.

## RTSP endpoint planning

The list-streams command derives candidate main/substream endpoint paths using the Hikvision NVR URI convention. It performs no network request and does not validate the RTSP port, authentication or path. Confirm these values on the target NVR before using a future live-stream feature.

## Scope

This configuration covers the Rust foundation, ISAPI connection and offline camera-channel/RTSP endpoint planning. Live stream session settings, zones, retention, notifications and model settings will be added with their corresponding features and documented validation rules.
