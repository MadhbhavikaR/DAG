# ADR-0002: System curl adapter for Hikvision ISAPI

- **Status:** Accepted
- **Date:** 2026-11-13
- **Decision scope:** HTTP Digest transport and XML parsing boundary

## Context

The Hikvision NVR exposes device identity and event notifications through ISAPI over HTTP. The target Jetson Nano uses JetPack 4.6.6 / Ubuntu 18.04 userspace. Credentials must not be exposed in process arguments or logs, and the application must not implement its own Digest cryptography.

## Decision drivers

- Mature and maintained Digest implementation.
- Avoid custom authentication and cryptographic code.
- Avoid Rust FFI and target-specific libcurl linkage in the first milestone.
- Bounded memory and predictable process lifecycle.
- Secret-safe credential handling.

## Options considered

1. Rust bindings to system libcurl.
2. System curl subprocess using stdin configuration.
3. Custom HTTP and Digest implementation.

## Decision

Use system curl as a transport adapter, invoked with \`std::process::Command\` and no shell. Pass request configuration and credentials through stdin using \`--config -\`, with \`-q\` as the first option. Never place credentials in argv. Use Digest authentication and fail closed; do not downgrade to Basic.

Parse XML using pinned quick-xml. Bound the stream reader channel and event document size. Reconnect with capped backoff.

## Consequences

### Positive
- Reuses maintained libcurl authentication behavior.
- Avoids custom cryptography and native Rust FFI.
- Keeps the Rust dependency graph small.
- Credentials do not appear in process command-line arguments.

### Negative
- Requires a system curl executable with compatible Digest support.
- Requires child process and pipe lifecycle management.
- HTTP on port 80 does not encrypt event contents.

### Neutral
- Physical NVR firmware, Digest algorithm and event payload compatibility still require hardware validation.

## Security and NFR implications

Use a dedicated least-privilege account and a trusted isolated LAN. Keep secrets in protected environment configuration. Bound stdout buffering, parser memory and stderr capture. Do not log raw XML or credentials.

## Validation and revisit triggers

Verify curl version and Digest algorithm against the actual NVR. Revisit if authentication fails due to libcurl capabilities or process lifecycle/latency measurements are unacceptable.

## References

- [curl manual](https://curl.se/docs/manpage.html)
- [Hikvision ISAPI integration center](https://tpp.hikvision.com/tpp/IntegrationCenter)
- [quick-xml documentation](https://docs.rs/quick-xml/0.38.3/quick_xml/)
