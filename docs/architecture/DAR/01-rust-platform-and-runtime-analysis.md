# DAR-001: Rust platform and runtime analysis

- **Status:** Initial analysis; target-device validation pending
- **Date:** 2026-11-13
- **Decision:** Select the Rust runtime/dependency baseline for Jetson Nano 4GB

## Problem and constraints

The application must run on Jetson Nano 4GB with JetPack 4.6.6 / L4T 32.7.6. The NVR is reachable at 192.168.100.103 on HTTP port 80. There are 13 allocated channels. RTSP is accessed through the NVR; port 554 is a default to verify, not a confirmed fact.

NVIDIA states JetPack 4.6.6 is the final JetPack 4 release. The platform is based on the legacy L4T R32 line and Ubuntu 18.04 userspace. Current crate versions may have MSRV or native-library requirements that cannot be assumed to work on this platform.

## Decision criteria

1. ARM64 and Ubuntu 18.04 userspace compatibility.
2. Build reproducibility and dependency pinning.
3. Low memory and CPU overhead.
4. Native GStreamer/TensorRT interoperability.
5. Long-term maintainability and security posture.
6. Availability of host CI and hardware-in-the-loop verification.

## Options

### A. Latest Rust compiler and latest dependencies
- Benefit: current language and ecosystem features.
- Risk: dependency MSRV and system-library requirements may exceed the device baseline.

### B. Pinned Rust toolchain and dependency versions
- Benefit: reproducible builds and explicit compatibility envelope.
- Risk: requires periodic controlled upgrades and security review.

### C. Build on device only
- Benefit: validates actual target ABI and native libraries.
- Risk: slower builds and limited reproducibility.

### D. Cross-compile on CI only
- Benefit: fast and repeatable CI.
- Risk: cannot prove runtime compatibility with the target's installed libraries.

## Analysis and recommendation

Use a pinned Rust toolchain and pinned dependency graph. Establish host CI for formatting, linting, tests and ARM64 build checks where practical. Perform a native build and runtime smoke test on the Jetson before declaring compatibility. Do not choose async/runtime, RTSP or inference crates solely from current popularity; check their declared MSRV, feature flags, transitive dependencies, libc assumptions and native library linkage.

A lightweight runtime is preferred. Tokio is a candidate for asynchronous I/O, but its current upstream MSRV is a moving target; select a version compatible with the pinned compiler only after verifying the target build. Avoid enabling broad default feature sets without need.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Dependency MSRV exceeds target toolchain | Pin toolchain and lockfile; verify in CI and on device |
| glibc/native ABI mismatch | Build and execute on target; inspect dynamic dependencies |
| Legacy platform security exposure | Isolate LAN, minimize services, maintain dependency inventory |
| Cross-build differs from target | Require hardware smoke test before release |
| Resource overcommit | Keep bounded concurrency and measure RSS/CPU/thermal behavior |

## Review outcome

Accepted as the discovery strategy. Exact compiler version, crate versions and native bindings remain open until F-001 research and target validation are complete.

## References

- [NVIDIA JetPack 4.6.6](https://developer.nvidia.com/jetpack-sdk-466)
- [NVIDIA Jetson Linux R32.7.6](https://developer.nvidia.com/embedded/linux-tegra-r3276)
- [Tokio MSRV policy](https://github.com/tokio-rs/tokio)
