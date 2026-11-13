# Project execution tracker

**Project:** DAG Nano 4GB NVR AI  
**Working branch:** `DAG-Nano-4gb-NVR-AI` (only permitted development branch)  
**Current baseline:** 0.1.0 (inherited template metadata; Rust application bootstrap not yet completed)  
**Status legend:** `[ ] pending` · `[~] in progress` · `[x] verified complete` · `[!] blocked`  
**Rule:** A checkbox becomes `[x]` only after the stated evidence exists. Hardware-only checks remain pending until run on the Nano/NVR.

## Global completion criteria

- [ ] All application modules run as one configurable Rust modular monolith.
- [ ] All required features have tests mirroring the source tree.
- [ ] CI, release automation, security controls, operations and documentation meet `AGENTS.md`.
- [ ] Quick Start works from a clean JetPack 4.6.6 installation.
- [ ] Sustained operation and resource use are measured on the actual Jetson Nano 4GB.
- [ ] All feature TODOs and release blockers are closed.

## Feature F-001 — Rust workspace and engineering foundation

**Type:** Atomic feature  
**Target version on completion:** 0.2.0  
**Status:** [ ] pending

### Research and design
- [x] Confirm ARM64 Rust toolchain target support; the official target table lists aarch64-unknown-linux-gnu as Tier 1.
- [x] Research baseline libc compatibility: Rust documents glibc 2.17+ for aarch64-unknown-linux-gnu; target runtime/linker validation on the Nano remains pending.
- [ ] Select and pin a Rust MSRV that can be installed and built on the target.
- [x] Establish dependency MSRV/native-library evaluation as a prerequisite; no runtime crates selected yet.
- [ ] Define workspace boundaries and dependency direction.
- [ ] Define configuration precedence, validation, secret handling and example files.
- [ ] Record workspace and compatibility decisions in ADR/DAR.

### Implementation
- [ ] Replace the Python template package with a Rust Cargo workspace.
- [ ] Add the application binary and minimal startup/shutdown lifecycle.
- [ ] Add typed application configuration with validation.
- [ ] Add structured logging with secret redaction.
- [ ] Add a health/status command that does not require NVR credentials.
- [ ] Add bounded task and resource configuration defaults.
- [ ] Remove obsolete Python-specific template configuration and workflows.

### Tests and verification
- [ ] Add unit tests for configuration defaults and invalid values.
- [ ] Add tests for environment override precedence.
- [ ] Add tests proving secrets are not serialized or logged.
- [ ] Run rustfmt check, Clippy with warnings denied, unit tests and release build in CI.
- [ ] Verify ARM64 build and startup on Jetson Nano before marking hardware compatibility complete.

### Documentation and delivery
- [ ] Add Cargo and Rust toolchain instructions to Quick Start.
- [ ] Document supported target, MSRV, build prerequisites and known limitations.
- [ ] Update version metadata to 0.2.0 in the feature commit.
- [ ] Verify CI on the single working branch.
- [ ] Commit with `feat:` prefix and push.

## Feature F-002 — Hikvision ISAPI device discovery and event ingestion

**Type:** Atomic feature  
**Target version:** 0.3.0  
**Status:** [ ] pending  
**Dependency:** F-001

### Research and design
- [ ] Verify exact ISAPI device-info response on the user's NVR firmware.
- [ ] Verify Digest authentication behavior and least-privilege account permissions.
- [ ] Capture representative alertStream payloads for motion active/inactive, heartbeat and reconnect.
- [ ] Confirm actual event type strings, XML namespaces, channel identifiers and timestamp formats.
- [ ] Decide bounded multipart/XML framing strategy and maximum payload size.
- [ ] Record protocol assumptions and threat mitigations in ADR/DAR.

### Implementation
- [ ] Implement typed NVR connection configuration.
- [ ] Implement Digest-authenticated device-info probe.
- [ ] Implement persistent alertStream client with explicit connect/read timeouts.
- [ ] Implement bounded event document framing and XML parsing.
- [ ] Normalize source, channel, event type, state and source timestamp.
- [ ] Filter only configured event types and active transitions.
- [ ] Implement reconnect with capped exponential backoff and jitter.
- [ ] Implement cancellation and graceful shutdown.
- [ ] Emit structured diagnostics without credentials or full sensitive payloads.

### Tests and verification
- [ ] Mirror NVR source modules under tests.
- [ ] Test XML namespaces, fragmented chunks, multiple messages per chunk and malformed XML.
- [ ] Test oversized and incomplete payload rejection.
- [ ] Test event active/inactive normalization and unknown event types.
- [ ] Test reconnect, timeout, cancellation and server disconnect using a mock HTTP server.
- [ ] Verify NVR device-info and motion event delivery on hardware.

### Documentation and delivery
- [ ] Document NVR account permissions, HTTP/ISAPI settings and LAN security.
- [ ] Document actual channel mapping only after discovery.
- [ ] Update Quick Start and configuration reference.
- [ ] Update version to 0.3.0 in the feature commit.
- [ ] Commit with `feat:` prefix and push.

## Feature F-003 — NVR RTSP discovery and bounded stream access

**Type:** Atomic feature  
**Target version:** 0.4.0  
**Status:** [ ] pending  
**Dependency:** F-002

- [ ] Research actual NVR RTSP URI and stream profile behavior.
- [ ] Verify RTSP credentials, transport mode and port on the target NVR.
- [ ] Implement secret-safe RTSP URI construction.
- [ ] Implement on-demand substream session management.
- [ ] Add explicit decoder/session limits, timeouts and cancellation.
- [ ] Test URI encoding, channel bounds, stream selection and failure recovery.
- [ ] Verify one and then multiple camera substreams on Jetson.
- [ ] Document verified channel mapping and resource measurements.

## Subsequent feature roadmap

- [ ] F-004 — Event routing, deduplication, bounded priority queue and SQLite persistence.
- [ ] F-005 — Video frame acquisition and bounded pre/post-event evidence buffer.
- [ ] F-006 — TensorRT human/vehicle detection integration.
- [ ] F-007 — Object tracking and track lifecycle.
- [ ] F-008 — Configurable polygon intrusion and virtual-fence rules.
- [ ] F-009 — Telegram notifications and rate limiting.
- [ ] F-010 — Face-presence detection with privacy controls (not identity recognition by default).
- [ ] F-011 — Temporal event analysis for suspected accidents and object throwing; human review and measured confidence required.
- [ ] F-012 — Optional Mirage evaluation behind a replaceable inference interface.
- [ ] F-013 — systemd deployment, health monitoring, log rotation, backup/retention and recovery.
- [ ] F-014 — End-to-end, soak, performance, security and release qualification.

## NFR verification ledger

- [ ] Performance: measure event-to-processing latency, frame rate, decode load and inference latency on device.
- [ ] Memory: measure steady-state and peak RSS; enforce configured memory/queue limits.
- [ ] Reliability: run reconnect and soak tests; verify no unbounded growth.
- [ ] Security: secret redaction, least privilege, LAN-only access, dependency audit and secure defaults.
- [ ] Maintainability: module boundaries, docs, ADR/DAR traceability and mirrored tests.
- [ ] Operability: health status, structured logs, clear diagnostics and automated restart.
- [ ] Privacy: retention policy, access controls, configurable face-presence processing and notification redaction.
