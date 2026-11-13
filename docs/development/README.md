# Development

Read the root [AGENTS.md](../../AGENTS.md) before changing the repository.

## Toolchain

The repository pins Rust 1.100.0 and declares Rust 1.85 as its MSRV. The initial foundation uses the Rust 2021 edition and no third-party runtime crates.

## Quality commands

\`\`\`bash
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --all-targets
cargo build --locked --release
\`\`\`

For the Jetson ARM64 target from an x86_64 Linux host, install \`gcc-aarch64-linux-gnu\`, add Rust target \`aarch64-unknown-linux-gnu\`, then run:

\`\`\`bash
CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER=aarch64-linux-gnu-gcc \\
  cargo build --locked --release --target aarch64-unknown-linux-gnu
\`\`\`

A cross-build does not replace native testing on Jetson Nano. Keep hardware checks marked pending until run on the device.
