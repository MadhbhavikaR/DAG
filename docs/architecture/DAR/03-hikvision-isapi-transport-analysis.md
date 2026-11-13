# DAR-003: Hikvision ISAPI transport and event parsing

- **Status:** Accepted and implemented in F-002; hardware compatibility validation pending
- **Date:** 2026-11-13
- **Scope:** HTTP transport, credential handling, event framing and XML parsing

## Decision statement

Use the system \`curl\` executable for the first ISAPI transport adapter, invoked directly without a shell. Supply request options and credentials through curl's stdin config interface. Use HTTP Digest authentication only. Parse alertStream XML with \`quick-xml\` and a bounded EventNotificationAlert document framer.

Pin \`quick-xml = 0.38.3\` and \`memchr = 2.7.5\` with a committed Cargo.lock. Require curl as an explicit OS dependency and inspect its version before connecting.

## Context and constraints

- NVR: Hikvision DS-7616NXI-K1, firmware V4.83.010 build 241118.
- HTTP endpoint: \`192.168.100.103:80\`.
- Event endpoint: \`GET /ISAPI/Event/notification/alertStream\`.
- Jetson Nano 4GB runs JetPack 4.6.6 / L4T 32.7.6 / Ubuntu 18.04.
- Secrets must not appear in process arguments, source, logs or committed configuration.
- Network input must be bounded and treated as untrusted.

## Options considered

### A. Rust curl bindings over system libcurl
Native API, but introduces a Rust FFI/native-library dependency, libcurl development headers and target-specific build/link validation.

### B. System curl subprocess with stdin config
Reuses maintained libcurl Digest behavior, avoids custom cryptography and a new Rust HTTP stack. Credentials can be passed through stdin rather than argv. Requires curl installation and careful child/pipe lifecycle management.

### C. Implement HTTP and Digest in Rust
Rejected because it duplicates security-sensitive protocol and cryptographic behavior.

## Decision and rationale

Select option B for F-002. Invoke \`curl\` with \`-q\` as the first option to prevent user curlrc loading, followed by \`--config -\` to read options from stdin. Use \`--digest\`, \`--no-buffer\`, \`--connect-timeout\`, \`--max-time 0\`, \`--fail\`, \`--silent\`, \`--show-error\`, \`--noproxy *\` and an XML Accept header.

The URL and credentials are written only to child stdin. Username/password are not placed in argv. Control characters are rejected and curl config quoting is escaped. Config buffers and credential byte buffers are cleared after use/drop. Never log request config, credentials or raw event payloads.

A bounded channel connects the curl stdout reader to the parser. Event documents are limited to 256 KiB. The framer discards multipart headers/boundary noise and retains only a possible partial opening marker.

Use quick-xml's pull reader with reusable buffers. Reject DTD declarations. Extract only known fields: eventType, eventState, channelID, dateTime and device identity fields.

## Event normalization

Only supported motion event types in an active state become MotionEvent values. Inactive transitions and unrelated events are ignored. Preserve source timestamp and NVR channel identifier. Physical camera mapping is not inferred from the number of cameras.

## Security and NFR analysis

- HTTP Digest does not encrypt the event stream. HTTP port 80 traffic remains readable on the network. Use a trusted isolated LAN; never port-forward ISAPI or RTSP.
- Use a dedicated least-privilege NVR account.
- Supply credentials only through protected environment variables or a protected systemd environment file.
- Do not put credentials in process arguments, logs, error strings or tracked files.
- Avoid shell execution and command interpolation.
- Drain stderr continuously with a bounded diagnostic capture.
- Bound reader channels and XML buffers to prevent memory growth.
- Reconnect with capped exponential backoff and jitter.
- Measure process memory, reconnect behavior and event latency on Jetson.

## Risks and validation gaps

| Risk | Mitigation / validation |
|---|---|
| curl absent | Preflight version check and documented package installation |
| curl Digest hash support differs from NVR | Verify actual NVR auth algorithm on hardware |
| Event payload differs by firmware | Capture V4.83.010 fixtures and extend parser tests |
| Stream framing malformed/oversized | Strict bounded framer and parser tests |
| HTTP content unencrypted | Trusted LAN/VLAN; investigate NVR HTTPS separately |
| CLI process termination | systemd process-group termination; add signal-aware shutdown in operations milestone |

## Review and revisit triggers

Revisit the transport if curl cannot authenticate with the NVR's configured Digest algorithm, child process lifecycle proves unreliable, or measured overhead is unacceptable. Do not silently downgrade to Basic authentication.

## References

- [Hikvision ISAPI integration center](https://tpp.hikvision.com/tpp/IntegrationCenter)
- [Hikvision NVR user manual](https://www.hikvision.com/content/dam/hikvision/products/S000000001/S000000002/S000000007/S000000026/OFR000040/M000000564/User_Manual/UD33768B_Baseline_Network-Video-Recorder-I-and-M-Series_User-Manual_V4.63.010_20230609.pdf)
- [curl manual](https://curl.se/docs/manpage.html)
- [quick-xml 0.38.3 documentation](https://docs.rs/quick-xml/0.38.3/quick_xml/)
