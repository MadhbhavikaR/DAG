# Architecture

## Architecture principles

- Rust-first, configurable modular monolith.
- Event-driven processing: the NVR remains the recorder and first-stage event source.
- Bounded resources and explicit backpressure.
- Inference only for selected event-triggered streams.
- Domain logic separated from ISAPI, RTSP, inference, persistence and notification adapters.
- Hardware-specific capabilities must be verified on the actual NVR and Jetson.

## Records

- [Architecture Decision Records (ADR)](ADR/README.md)
- [Decision Analysis and Review (DAR)](DAR/README.md)

## Current system context

The target system has a Hikvision DS-7616NXI-K1 NVR at `192.168.100.103:80`, 13 allocated channels, and a Jetson Nano 4GB running JetPack 4.6.6. Camera-to-channel allocation and event payload details remain subject to device discovery.

## Quality attributes

Performance, memory footprint, availability, recoverability, security, privacy, configurability, testability and maintainability are first-class design constraints.
