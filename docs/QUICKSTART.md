# Quick Start

> **Current status: bootstrap in progress.** The Rust workspace and deployment commands are not yet implemented. This guide will become executable as Feature F-001 is completed. Do not use the old Python template instructions for this project.

## Target hardware

- Jetson Nano 4GB
- JetPack 4.6.6 / Jetson Linux L4T 32.7.6
- Hikvision DS-7616NXI-K1 NVR
- NVR address: `192.168.100.103`
- HTTP/ISAPI port: `80`
- RTSP port: `554` (configured assumption; verify on device)
- 13 allocated NVR channels; physical camera-to-channel mapping is not yet verified

## Planned first-run flow

1. Verify the Jetson release, architecture, available disk, RAM and thermal state.
2. Install or verify the pinned Rust toolchain and native build prerequisites.
3. Clone the repository and switch to the sole working branch.
4. Copy the example configuration to the local configuration path.
5. Supply NVR credentials through a protected environment file; never commit them.
6. Run configuration validation and the local health command.
7. Probe NVR device information.
8. Start event ingestion and verify a test motion event.
9. Verify one RTSP substream before enabling additional channels.

## Repository checkout

```bash
git clone https://github.com/MadhbhavikaR/DAG.git
cd DAG
git switch DAG-Nano-4gb-NVR-AI
```

## Credentials and network security

Use a dedicated NVR integration account with only the permissions required by the application. Keep the NVR and Jetson on a trusted LAN. Do not port-forward HTTP/ISAPI or RTSP to the Internet. Store credentials in a protected local secret file with restrictive permissions or an equivalent secret mechanism. The application must redact secrets from logs.

## Status

The exact install/build/run commands will be added only after they have been tested in CI and, for hardware-specific steps, on the Jetson Nano.
