# DAR-003: Hikvision ISAPI transport and event parsing

- **Status:** Accepted for F-002 implementation; hardware compatibility validation pending
- **Date:** 2026-11-13
- **Scope:** HTTP transport, credential handling, event framing and XML parsing for the NVR

## Decision statement

Implement the first ISAPI transport adapter using the system \`curl\` executable, invoked directly without a shell. Supply options and credentials through curl's stdin config interface. Use HTTP Digest authentication only. Parse the event stream with \`quick-xml\` and a bounded EventNotificationAlert document framer.

Pin \`quick-xml = 0.38.3\` and \`memchr = 2.7.5\` with a committed Cargo.lock. Require the curl executable as an explicit OS dependency and validate its presence/version before connecting.

## Context and constraints

- NVR: Hikvision DS-7616NXI-K1, firmware V4.83.010 build 241118.
- HTTP endpoint: \`192.168.100.103:80\`.
- Event endpoint: \`GET /ISAPI/Event/notification/alertStream\`.
- The endpoint establishes a persistent connection and sends event/heartbeat XML messages.
- Jetson Nano 4GB runs JetPack 4.6.6 / L4T 32.7.6 / Ubuntu 18.04.
- Secrets must not appear in process arguments, source, logs, or committed configuration.
- Network input must be bounded and treated as untrusted.

## Options considered

### A. Rust curl bindings over system libcurl

Advantages: native Rust API, no external curl process, Digest authentication supported by libcurl.

Disadvantages: introduces a Rust FFI/native-library dependency, requires libcurl development headers and a compatible build/link path on JetPack 4.6.6, and expands the Cargo dependency graph.

### B. System curl subprocess with stdin config

Advantages: reuses mature libcurl behavior and system authentication/TLS support; no custom Digest implementation; credentials can be passed in a config read from stdin; no secret-bearing command-line arguments; no extra Rust HTTP stack.

Disadvantages: requires a curl executable, introduces process lifecycle management, and requires robust stdout/stderr draining and restart behavior.

### C. Implement HTTP and Digest authentication in Rust

Advantages: no external transport executable.

Disadvantages: duplicates security-sensitive protocol and cryptographic behavior. This is rejected; authentication should be delegated to a maintained implementation.

## Decision and rationale

Select option B for F-002. Invoke \`curl\` using \`std::process::Command\` (never a shell), with \`-q\` as the first option to prevent loading user curlrc configuration, followed by \`--config -\` to read request options from stdin. Use \`--digest\`, \`--no-buffer\`, \`--connect-timeout\`, \`--max-time 0\`, \`--fail\`, \`--silent\`, \`--show-error\`, and \`--noproxy *\`.

The URL and credentials are written only to the child process stdin. The username/password are not placed in argv. Reject control characters and correctly escape curl config quoting. Do not log config text, stdout payloads or credentials.

Use a bounded channel between the curl stdout reader and event parser. Apply a maximum event document size (256 KiB) and discard unrelated multipart boundary/header bytes while retaining only the suffix needed to detect a split opening tag.

Use quick-xml pull parsing with reusable buffers. Do not implement a general XML parser. Do not enable external entity expansion or accept DTD/entity declarations. Extract only known leaf fields: eventType, eventState, channelID, dateTime, eventDescription and ipAddress.

## Event normalization

Only configured motion event types in an active state are emitted as motion events. Inactive transitions and heartbeat events are not new motion alerts. Preserve source timestamp and NVR channel identifier. Physical camera mapping is a separate discovery item and must not be inferred from the channel count.

## Security and NFR analysis

- HTTP Digest avoids sending the password as Basic authentication, but HTTP on port 80 does not encrypt event contents. Keep traffic on a trusted isolated LAN; do not port-forward HTTP or RTSP.
- Use a dedicated least-privilege NVR account.
- Supply credentials only through protected environment variables or a protected systemd environment file; never through tracked config.
- Do not put credentials in process arguments, logs or error strings.
- Avoid shell execution and command interpolation.
- Drain stderr continuously but retain only a bounded diagnostic sample.
- Bound reader channels and XML buffers to prevent memory growth.
- Reconnect with capped exponential backoff and jitter.
- Treat curl exit/status failures as recoverable except missing executable or invalid local configuration.
- Measure persistent process memory, reconnect behavior and event latency on the Jetson.

## Risks and validation gaps

| Risk | Mitigation / validation |
|---|---|
| curl not installed | Preflight check and documented package installation |
| curl build lacks required Digest hash backend | Inspect \`curl --version\`; verify actual NVR auth on hardware |
| NVR requires Digest SHA-256 unsupported by installed curl | Verify on device; if incompatible, evaluate a pinned Rust curl binding/system libcurl upgrade |
| Event payload differs by firmware | Capture and fixture real V4.83.010 payloads |
| Stream framing malformed or oversized | Strict bounded framer and parser tests |
| HTTP content is unencrypted | Trusted LAN/VLAN; investigate NVR HTTPS support separately |

## Review and revisit triggers

Revisit the transport choice if the Nano's curl version cannot authenticate with the NVR's configured Digest algorithm, if child process lifecycle proves unreliable, or if measured overhead is unacceptable. Do not silently downgrade to Basic authentication.

## References

- [Hikvision NVR user manual: ISAPI and HTTP Digest authentication](https://www.hikvision.com/content/dam/hikvision/products/S000000001/S000000002/S000000007/S000000026/OFR000040/M000000564/User_Manual/UD33768B_Baseline_Network-Video-Recorder-I-and-M-Series_User-Manual_V4.63.010_20230609.pdf)
- [Hikvision ISAPI integration center](https://tpp.hikvision.com/tpp/IntegrationCenter)
- [Hikvision ISAPI alertStream developer-guide mirror](https://raw.githubusercontent.com/loozhengyuan/hikvision-sdk/master/resources/isapi.pdf)
- [curl manual: config from stdin](https://curl.se/docs/manpage.html)
- [curl Digest authentication](https://curl.se/docs/manpage.html)
- [quick-xml documentation](https://docs.rs/quick-xml/0.38.3/quick_xml/)
