# DAG Nano 4GB NVR AI

Event-driven NVR monitoring and AI orchestration for a Hikvision DS-7616NXI-K1 NVR and 13 allocated channels, using a Jetson Nano 4GB as a selective AI processor.

## Project status

The Rust foundation is implemented in version 0.2.3. NVR connectivity, RTSP ingestion and AI inference are subsequent features and are not yet implemented.

## Target hardware

- Hikvision DS-7616NXI-K1, firmware V4.83.010 build 241118
- NVR address: 192.168.100.103
- HTTP/ISAPI port: 80
- RTSP port: 554 (verify on the NVR before integration)
- 13 allocated channels; physical channel mapping remains to be discovered
- 11 Hikvision DS-2CD1041G2-LIU cameras
- 2 CP Plus CP-UNC-TA41L3C-D-LQ cameras
- Jetson Nano 4GB, JetPack 4.6.6 / L4T 32.7.6

## Quick Start

See [docs/QUICKSTART.md](docs/QUICKSTART.md).

Install the pinned Rust toolchain, then validate configuration:

\`\`\`bash
cargo run --locked -- validate-config --config=config/dag-nvr-ai.example.conf
cargo run --locked -- health
cargo test --locked
\`\`\`

## Architecture

The NVR remains the continuous recorder and first-stage motion event source. The Jetson will consume NVR events, retrieve only relevant streams, and progressively add detection, tracking, zone rules and notifications.

The application is a configurable, event-driven Rust modular monolith. AI inference will use a replaceable adapter around the JetPack-compatible TensorRT/CUDA stack; the Rust core will own orchestration, rules, storage and notifications.

## Development

Read [AGENTS.md](AGENTS.md) before contributing. Work only on branch \`DAG-Nano-4gb-NVR-AI\`. The root [todo.md](todo.md) is the project execution source of truth.

CI runs formatting, Clippy, tests, an optimized host build and an ARM64 Linux cross-build. Hardware validation on the Jetson is still required before claiming deployment compatibility.

## Documentation

- [Quick Start](docs/QUICKSTART.md)
- [Documentation index](docs/README.md)
- [Architecture ADRs](docs/architecture/ADR/README.md)
- [Decision Analysis and Review](docs/architecture/DAR/README.md)
- [Configuration](docs/configuration/README.md)
- [Development](docs/development/README.md)
