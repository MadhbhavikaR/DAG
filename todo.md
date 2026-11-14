# Project execution tracker

**Project:** DAG Nano 4GB NVR AI  
**Working branch:** DAG-Nano-4gb-NVR-AI (only permitted development branch)  
**Current baseline:** 0.4.0 (F-003 camera inventory and candidate RTSP URI planning implemented; hardware validation pending)  
**Status legend:** [ ] pending · [~] in progress · [x] verified complete · [!] blocked  
**Rule:** A checkbox becomes [x] only after the stated evidence exists. Hardware-only checks remain pending until run on the Nano/NVR.

## Global completion criteria

- [ ] All application modules run as one configurable Rust modular monolith.
- [ ] All required features have tests mirroring the source tree.
- [ ] CI, release automation, security controls, operations and documentation meet AGENTS.md.
- [ ] Quick Start works from a clean JetPack 4.6.6 installation.
- [ ] Sustained operation and resource use are measured on the actual Jetson Nano 4GB.
- [ ] All feature TODOs and release blockers are closed.

## F-001 — Rust workspace and engineering foundation

**Status:** [~] CI quality suite and ARM64 cross-build passed; native Jetson validation pending.

- [x] Rust package, CLI, typed configuration and JSON-lines logging.
- [x] Health/version/config-validation commands.
- [x] Strict configuration validation and environment overrides.
- [x] CI formatting, Clippy, tests, optimized build and ARM64 cross-build.
- [ ] Native build and startup on Jetson Nano.

## F-002 — Hikvision ISAPI device discovery and event ingestion

**Status:** [~] CI quality suite and ARM64 cross-build passed; NVR hardware validation pending.

- [x] Digest-authenticated device-info probe using system curl.
- [x] Persistent alertStream reader and bounded XML framing/parsing.
- [x] Active motion-event normalization and reconnect backoff.
- [x] Credentials passed through stdin configuration, not process arguments.
- [x] DAR-003 and ADR-0002 document transport alternatives and security.
- [ ] Verify Digest compatibility and event delivery on the exact NVR firmware.
- [ ] Confirm actual channel IDs and event payload semantics.
- [ ] Add explicit signal-aware graceful shutdown and mock-server reconnect tests.

## F-003 — Camera channel inventory and candidate RTSP URI planning

**Type:** Atomic feature  
**Version:** 0.4.0  
**Status:** [x] Software implementation and CI verification required; hardware validation remains pending.  
**Dependency:** F-002

- [x] Add strict optional CHANNEL_ID=LABEL mapping with generic fallback labels.
- [x] Validate channel bounds, duplicate mappings and safe labels.
- [x] Generate candidate main/substream paths for up to 16 channels.
- [x] Add list-streams CLI with configurable application and camera-map paths.
- [x] Ensure URI generation never accepts or prints credentials.
- [x] Add unit/integration tests for URI paths, profiles, labels, invalid input and CLI output.
- [x] Add Quick Start, configuration docs, ADR-0003 and DAR-004.
- [ ] Verify RTSP port, URI convention, channel numbering and stream suffixes on hardware.
- [ ] Verify authentication and transport behavior on the target NVR.
- [ ] Benchmark a single substream on Jetson before adding live session management.

## F-004 — Credential-safe RTSP session and bounded substream access

**Status:** [ ] pending  
**Dependency:** F-003 hardware URI validation.

- [ ] Evaluate JetPack 4.6.6-compatible GStreamer and FFmpeg integration.
- [ ] Select a credential-safe authentication mechanism; never put secrets in URI or process arguments.
- [ ] Implement on-demand substream sessions with TCP transport, deadlines and cancellation.
- [ ] Enforce a strict decoder/session limit and bounded frame buffers.
- [ ] Add mock/failure tests and hardware-in-the-loop stream tests.
- [ ] Measure RSS, CPU, GPU/decoder load, latency and thermal behavior on Jetson.

## Subsequent feature roadmap

- [ ] F-005 — Event routing, deduplication, bounded priority queue and SQLite persistence.
- [ ] F-006 — Video frame acquisition and bounded pre/post-event evidence buffer.
- [ ] F-007 — TensorRT human/vehicle detection integration.
- [ ] F-008 — Object tracking and track lifecycle.
- [ ] F-009 — Configurable polygon intrusion and virtual-fence rules.
- [ ] F-010 — Telegram notifications and rate limiting.
- [ ] F-011 — Face-presence detection with privacy controls (not identity recognition by default).
- [ ] F-012 — Temporal event analysis for suspected accidents and object throwing; human review and measured confidence required.
- [ ] F-013 — Optional Mirage evaluation behind a replaceable inference interface.
- [ ] F-014 — systemd deployment, health monitoring, log rotation, backup/retention and recovery.
- [ ] F-015 — End-to-end, soak, performance, security and release qualification.

## NFR verification ledger

- [ ] Performance: measure event-to-processing latency, frame rate, decode load and inference latency on device.
- [ ] Memory: measure steady-state and peak RSS; enforce configured memory/queue limits.
- [ ] Reliability: run reconnect and soak tests; verify no unbounded growth.
- [ ] Security: secret redaction, least privilege, LAN-only access, dependency audit and secure defaults.
- [ ] Maintainability: module boundaries, docs, ADR/DAR traceability and mirrored tests.
- [ ] Operability: health status, structured logs, clear diagnostics and automated restart.
- [ ] Privacy: retention policy, access controls, configurable face-presence processing and notification redaction.
