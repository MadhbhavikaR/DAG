# DAR-002: Rust workspace baseline, dependency policy and configuration

- **Status:** Recommended for F-001 implementation
- **Date:** 2026-11-13
- **Scope:** Toolchain, language edition, initial dependency footprint, configuration and CI

## Decision statement

Establish a Rust 2021 application using a pinned Rust 1.100.0 toolchain and declared MSRV 1.85. Begin with a single-package Cargo workspace and no third-party runtime dependencies. Use a deliberately small UTF-8 KEY=VALUE configuration format for the foundation, with precedence defaults < config file < environment variables.

## Constraints and decision criteria

- Jetson Nano 4GB, ARM64, JetPack 4.6.6 / L4T 32.7.6 / Ubuntu 18.04.
- Official Rust target `aarch64-unknown-linux-gnu` requires glibc 2.17+; the target OS is expected to provide glibc 2.27, but the actual device must be checked.
- Stable compiler reproducibility, native build compatibility, small dependency graph, low memory and maintainable CI.
- No credentials or tokens in tracked configuration.
- A clean Quick Start and testable configuration validation.

## Options considered

### Toolchain
- Unpinned stable: automatically adopts new compilers and may change build outcomes.
- Pinned current stable: reproducible CI and developer builds; deliberate updates are required.
- Old fixed compiler: potentially less suitable for current security fixes and tool support.

**Selection:** pin Rust 1.100.0 for CI/development; declare 1.85 as the source MSRV. Revisit with each controlled toolchain update and verify on the target.

### Language edition
- Rust 2021: mature and supported by the pinned compiler.
- Rust 2024: requires Rust 1.85 or newer and introduces edition migration considerations.

**Selection:** Rust 2021 for the initial baseline. Edition choice is not used as a proxy for MSRV.

### Dependencies
- Add async, config, logging and error crates immediately.
- Start with standard library only and add a crate when a feature needs it.

**Selection:** standard library only for F-001. This minimizes attack surface, compile time, lockfile complexity and ABI uncertainty. Third-party dependencies will be evaluated and pinned per feature, not prohibited.

### Configuration format
- TOML/Serde: established format and rich typing, but adds dependency and MSRV considerations.
- YAML: readable but adds parser dependencies and more complex implicit typing.
- Small KEY=VALUE file: limited expressive power but trivial parser, no dependency and explicit validation.

**Selection:** KEY=VALUE for the initial deployment settings only. If nested camera/zones/model configuration becomes necessary, reassess TOML with a pinned, audited parser in a separate DAR. Never build an ad-hoc general-purpose parser.

## Implementation outline

- One Cargo package named `dag-nvr-ai` with library and binary targets.
- Modules: configuration, structured logging, CLI/health.
- Validate configuration before any service startup.
- Environment variables override file values; file values override defaults.
- Strictly reject unknown keys, malformed values, invalid ranges and unsupported log levels.
- Avoid secrets in the initial config schema. NVR credentials are introduced with the NVR feature through a protected secret source.
- CI: format, Clippy, tests, release build, and ARM64 cross-build check.
- Use a GitHub Actions release workflow to run the release test suite once for each release tag before publishing.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| New stable compiler changes | Pin toolchain; upgrade through reviewed chore |
| ARM64 cross-build does not prove device ABI | Native Jetson smoke test remains a release gate |
| Standard-library config parser grows beyond scope | Keep grammar intentionally small; reassess before nested settings |
| No runtime dependencies delays feature work | Add only researched, pinned crates when the next feature requires them |
| GitHub runner differs from Nano | ARM64 cross-build plus hardware-in-the-loop verification |

## Review criteria

F-001 is accepted only when CI passes formatting, Clippy, tests, release build and ARM64 cross-build. Native Jetson startup and preflight remain explicitly pending until the target device is tested.

## References

- [Rust 1.100.0 release announcement (2026-11-12)](https://blog.rust-lang.org/2026/11/12/Rust-1.100.0/)
- [Rust aarch64-unknown-linux-gnu target support](https://doc.rust-lang.org/rustc/platform-support/aarch64-unknown-linux-gnu.html)
- [Cargo dependency resolver and MSRV behavior](https://doc.rust-lang.org/cargo/reference/resolver.html)
- [NVIDIA JetPack 4.6.6](https://developer.nvidia.com/jetpack-sdk-466)
