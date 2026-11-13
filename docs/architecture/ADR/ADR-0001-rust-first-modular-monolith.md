# ADR-0001: Rust-first configurable modular monolith

- **Status:** Accepted
- **Date:** 2026-11-13
- **Decision scope:** Application language, deployment topology and module boundaries

## Context

The target is a Jetson Nano 4GB running JetPack 4.6.6 and receiving motion events from a Hikvision DS-7616NXI-K1 NVR. The application must manage 13 allocated channels while keeping CPU, RAM, GPU memory, decoder sessions and inference concurrency bounded. A Python 3.12 template is not an appropriate runtime baseline for the JetPack 4 environment.

NVIDIA identifies JetPack 4.6.6 as the final JetPack 4 release and L4T 32.7.6 as its corresponding Jetson Linux release. It includes an Ubuntu 18.04-based sample filesystem. This creates a compatibility and lifecycle constraint for native dependencies and toolchains.

## Decision drivers

- Predictable memory behavior and safe concurrency.
- Efficient asynchronous network/event processing.
- Native interoperability with GStreamer, CUDA and TensorRT.
- Small operational footprint and a single deployable service.
- Testable boundaries and configurable behavior.
- Compatibility with the target's ARM64 userspace and native libraries.

## Options considered

1. Python-only application: faster prototyping but less aligned with the desired native runtime and target dependency constraints.
2. Rust modular monolith: memory-safe application core with native inference adapters.
3. Multiple microservices/containers: stronger process isolation but higher RAM, operational and deployment overhead on a 4GB device.

## Decision

Use a Rust-first modular monolith as the application runtime. Keep one deployable process with explicit internal modules for configuration, NVR, cameras, event routing, AI adapters, rules, storage, notifications and monitoring. Use TensorRT/CUDA for GPU inference through a narrow adapter boundary; do not reimplement GPU inference in Rust.

Use event-driven, on-demand stream acquisition. Apply bounded queues, backpressure, timeouts, cancellation and graceful shutdown.

## Consequences

### Positive
- Memory-safe core and explicit concurrency.
- One service with low orchestration overhead.
- Inference backend can be replaced behind an interface.
- Domain logic can be tested without physical cameras.

### Negative
- Native library integration and cross-compilation require careful validation.
- Rust crate MSRV and libc requirements must be pinned to the Jetson target.
- TensorRT integration may require a small C/C++ FFI boundary.

### Neutral
- Rust does not guarantee faster model inference than TensorRT; model execution performance is determined by the inference engine, model, precision, preprocessing and hardware.

## Security and NFR implications

- Bound all queues, payloads and concurrent streams.
- Use least-privilege NVR credentials and secret redaction.
- Do not expose NVR endpoints outside the trusted LAN.
- Measure memory, latency, CPU, thermals and reconnect stability on hardware.
- Treat JetPack 4 as a legacy/final software line and record the security maintenance implications.

## Validation and revisit triggers

Revisit this decision if the Rust toolchain or required native dependencies cannot be built and maintained on the Jetson's ARM64 Ubuntu 18.04 userspace, or if measured resource use fails the system's NFR budgets.

## References

- [NVIDIA JetPack 4.6.6](https://developer.nvidia.com/jetpack-sdk-466)
- [NVIDIA Jetson Linux R32.7.6](https://developer.nvidia.com/embedded/linux-tegra-r3276)
- [Tokio supported Rust versions](https://github.com/tokio-rs/tokio)
