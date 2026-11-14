# DAG Nano 4GB NVR AI

Event-driven NVR monitoring and AI orchestration for a Hikvision DS-7616NXI-K1 NVR and 13 allocated channels, using a Jetson Nano 4GB as a selective AI processor.

## Project status

Version 0.4.3 includes the Rust foundation, Hikvision ISAPI motion-event ingestion, configurable camera channel labels and candidate RTSP endpoint generation. Physical NVR/Jetson validation is still required. Live RTSP sessions, persistence, AI inference, tracking and Telegram notifications remain future features.

## Target hardware

- Hikvision DS-7616NXI-K1, firmware V4.83.010 build 241118
- NVR address: 192.168.100.103
- HTTP/ISAPI port: 80
- RTSP port: 554 (verify on the NVR before stream access)
- 13 allocated channels; physical channel mapping remains to be discovered
- 11 Hikvision DS-2CD1041G2-LIU cameras
- 2 CP Plus CP-UNC-TA41L3C-D-LQ cameras
- Jetson Nano 4GB, JetPack 4.6.6 / L4T 32.7.6

## Quick Start

See [docs/QUICKSTART.md](docs/QUICKSTART.md).

Probe NVR identity:

```bash
cargo run --locked -- probe-nvr --config=config/dag-nvr-ai.local.conf
```

Start motion-event ingestion:

```bash
cargo run --locked -- listen-events --config=config/dag-nvr-ai.local.conf
```

List candidate RTSP endpoints (no network connection is attempted):

```bash
cargo run --locked -- list-streams --config=config/dag-nvr-ai.local.conf --camera-map=config/cameras.example.conf
```

## Architecture

The NVR remains the continuous recorder and first-stage motion event source. The Jetson consumes NVR events and will retrieve only relevant camera streams for subsequent AI processing.

The application is a configurable, event-driven Rust modular monolith. The ISAPI adapter delegates HTTP Digest authentication to system curl, passes credentials through curl stdin configuration (not process arguments), and parses bounded XML documents with quick-xml. Camera channel labels are operator-supplied; candidate RTSP paths are generated offline and are not asserted to be valid until hardware-verified.

## Development

Read [AGENTS.md](AGENTS.md) before contributing. Work only on branch `DAG-Nano-4gb-NVR-AI`. The root [todo.md](todo.md) is the project execution source of truth.

CI runs formatting, Clippy, tests, an optimized host build and an ARM64 Linux cross-build. Hardware validation on the Jetson and NVR is still required before claiming operational compatibility.

## Documentation

- [Quick Start](docs/QUICKSTART.md)
- [Documentation index](docs/README.md)
- [Architecture ADRs](docs/architecture/ADR/README.md)
- [Decision Analysis and Review](docs/architecture/DAR/README.md)
- [Configuration](docs/configuration/README.md)
- [Development](docs/development/README.md)
