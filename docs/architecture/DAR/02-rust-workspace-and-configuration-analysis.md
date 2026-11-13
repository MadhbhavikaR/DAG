# DAR-002: Rust workspace baseline, dependency policy and configuration

- **Status:** Accepted for F-001
- **Date:** 2026-11-13
- **Scope:** Toolchain, language edition, initial dependency footprint, configuration and CI

## Decision statement

Establish a Rust 2021 application using a pinned Rust 1.100.0 toolchain and declared MSRV 1.85. Begin with a single-package Cargo workspace and no third-party runtime dependencies. Use a deliberately small UTF-8 KEY=VALUE configuration format for foundation settings, with precedence defaults < config file < environment variables.

## Constraints and criteria

- Jetson Nano 4GB, ARM64, JetPack 4.6.6 / L4T 32.7.6 / Ubuntu 18.04.
- Rust's official \`aarch64-unknown-linux-gnu\` target supports glibc 2.17+; expected target glibc is newer, but device verification is mandatory.
- Reproducible builds, small dependency graph, bounded resource defaults, maintainability and CI.
- No credentials or tokens in tracked configuration.

## Alternatives and analysis

### Toolchain
Unpinned stable adopts compiler changes automatically. An old fixed compiler risks missing fixes and tool support. Pinning current stable provides reproducibility while allowing reviewed upgrades.

**Decision:** pin Rust 1.100.0 for CI/development and declare 1.85 as MSRV. Validate actual device installation/build.

### Edition
Rust 2021 is mature and supported. Rust 2024 requires Rust 1.85 or newer and introduces edition migration considerations.

**Decision:** use Rust 2021 initially; edition and MSRV remain separate choices.

### Dependencies
Adding async, config and logging crates immediately increases dependency, compile and ABI surface. Standard-library-only foundations are adequate for startup, configuration and health diagnostics.

**Decision:** use no third-party runtime crates in F-001. Add pinned crates when a concrete feature requires them and after reviewing MSRV, native dependencies, security and ARM64 support.

### Configuration
TOML/Serde and YAML are expressive but add parser dependencies. A small KEY=VALUE file is intentionally limited and simple to validate.

**Decision:** use KEY=VALUE only for foundation settings. Do not grow it into a general-purpose parser. Reassess TOML for nested camera/zone/model configuration when needed.

## Implementation outline

- Single Cargo package named \`dag-nvr-ai\` with library and binary targets.
- Modules for configuration, structured logging and CLI/health.
- Validate before service startup.
- Precedence: defaults < config file < \`DAG_*\` environment values.
- Strictly reject unknown/duplicate keys, malformed lines and invalid ranges.
- Keep credentials out of this config schema.
- CI runs format, Clippy, tests, optimized host build and ARM64 cross-build.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Toolchain updates change build | Pin compiler and upgrade through reviewed chore |
| ARM64 cross-build differs from Nano | Require native Jetson smoke test |
| Config grammar becomes complex | Keep grammar small; revisit format before nested config |
| Dependency growth creates ABI/security burden | Add dependencies per feature with MSRV and license review |
| Resource settings are mistaken for measured capacity | Treat limits as safe defaults and benchmark on hardware |

## Acceptance and review

F-001 is complete only after CI succeeds for formatting, Clippy, tests, optimized host build and ARM64 cross-build. Native Jetson startup remains a separate hardware acceptance item.

## References

- [Rust 1.100.0 release announcement (2026-11-12)](https://blog.rust-lang.org/2026/11/12/Rust-1.100.0/)
- [Rust aarch64-unknown-linux-gnu target support](https://doc.rust-lang.org/rustc/platform-support/aarch64-unknown-linux-gnu.html)
- [Cargo dependency resolver](https://doc.rust-lang.org/cargo/reference/resolver.html)
- [NVIDIA JetPack 4.6.6](https://developer.nvidia.com/jetpack-sdk-466)
