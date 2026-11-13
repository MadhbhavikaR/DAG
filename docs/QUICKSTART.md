# Quick Start

## Target hardware

- Jetson Nano 4GB
- JetPack 4.6.6 / L4T 32.7.6 / Ubuntu 18.04 userspace
- Hikvision DS-7616NXI-K1 NVR at \`192.168.100.103:80\`
- 13 allocated NVR channels
- RTSP source: NVR; RTSP port 554 is a default assumption and must be verified

## 1. Install the pinned Rust toolchain

The repository pins Rust 1.100.0 in \`rust-toolchain.toml\`. Install rustup using the [official Rust installation instructions](https://www.rust-lang.org/tools/install), then install the repository toolchain:

\`\`\`bash
rustup toolchain install 1.100.0 --profile minimal --component rustfmt --component clippy
rustc --version
cargo --version
\`\`\`

On the Jetson, confirm the platform before building:

\`\`\`bash
uname -m
cat /etc/nv_tegra_release
ldd --version | head -n 1
free -h
\`\`\`

Expected architecture is \`aarch64\`. Record the actual glibc version and available disk/RAM during device validation.

## 2. Check out the only working branch

\`\`\`bash
git clone https://github.com/MadhbhavikaR/DAG.git
cd DAG
git switch DAG-Nano-4gb-NVR-AI
\`\`\`

## 3. Configure the application

Copy the example configuration:

\`\`\`bash
cp config/dag-nvr-ai.example.conf config/dag-nvr-ai.local.conf
\`\`\`

Edit the local file to match the NVR. The supplied example uses the discovered NVR address and 13 allocated channels. Verify the RTSP port before stream integration.

Configuration precedence:

1. Built-in safe defaults.
2. Values in the selected config file.
3. Environment variables prefixed with \`DAG_\`, which override file values.

Supported environment overrides include \`DAG_NVR_HOST\`, \`DAG_NVR_HTTP_PORT\`, \`DAG_NVR_RTSP_PORT\`, \`DAG_NVR_CHANNELS\`, \`DAG_EVENT_QUEUE_CAPACITY\`, \`DAG_MAX_CONCURRENT_INFERENCE\`, \`DAG_LOG_LEVEL\` and \`DAG_DATA_DIR\`.

The current foundation configuration does not contain usernames, passwords or tokens. Never commit secrets or local configuration.

## 4. Validate configuration and application health

\`\`\`bash
cargo run --locked -- validate-config --config=config/dag-nvr-ai.local.conf
cargo run --locked -- health
cargo run --locked -- version
\`\`\`

The health command is a local process check; it does not yet test NVR connectivity.

## 5. Run tests and build

\`\`\`bash
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --all-targets
cargo build --locked --release
\`\`\`

## Current scope and next feature

Version 0.2.5 provides the Rust application foundation, configuration validation, JSON-lines logging, health/version commands and CI cross-build checks. ISAPI event ingestion, RTSP stream retrieval, SQLite persistence, AI inference and Telegram notifications are not yet implemented.

See the root [todo.md](../todo.md) for the implementation sequence and hardware acceptance checks.
