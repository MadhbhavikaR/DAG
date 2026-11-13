# Configuration

The application will use validated configuration files with environment overrides for deployment-specific values and secrets.

Configuration precedence will be documented when implemented. No credentials belong in tracked files. Example configuration must contain placeholders or non-secret defaults only.

Planned configurable groups:

- NVR connection and authentication.
- Channel-to-camera mapping.
- RTSP port, stream selection and transport.
- Event types, deduplication and queue bounds.
- Decoder and inference concurrency.
- Detection thresholds and zones.
- Storage, retention and evidence handling.
- Telegram notification behavior.
- Logging, health checks and resource budgets.

Only settings implemented and validated by the application will appear in the final configuration reference.
