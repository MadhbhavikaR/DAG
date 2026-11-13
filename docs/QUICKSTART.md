# Quick Start

## Target hardware

- Jetson Nano 4GB
- JetPack 4.6.6 / L4T 32.7.6 / Ubuntu 18.04 userspace
- Hikvision DS-7616NXI-K1 NVR at \`192.168.100.103:80\`
- 13 allocated NVR channels
- RTSP source: NVR; RTSP port 554 is a default assumption and must be verified before RTSP integration

## 1. Install curl

The ISAPI transport uses the system curl executable with HTTP Digest authentication.

\`\`\`bash
sudo apt-get update
sudo apt-get install --no-install-recommends curl
curl --version
\`\`\`

The installed curl build must support the Digest algorithm configured on the NVR. Verify this with the actual NVR before relying on event delivery.

## 2. Install the pinned Rust toolchain

The repository pins Rust 1.100.0 in \`rust-toolchain.toml\`. Install rustup using the [official Rust installation instructions](https://www.rust-lang.org/tools/install), then install the repository toolchain:

\`\`\`bash
rustup toolchain install 1.100.0 --profile minimal --component rustfmt --component clippy
rustc --version
cargo --version
\`\`\`

Confirm the Jetson platform:

\`\`\`bash
uname -m
cat /etc/nv_tegra_release
ldd --version | head -n 1
free -h
\`\`\`

Expected architecture is \`aarch64\`. Record actual glibc version and available disk/RAM during device validation.

## 3. Check out the only working branch

\`\`\`bash
git clone https://github.com/MadhbhavikaR/DAG.git
cd DAG
git switch DAG-Nano-4gb-NVR-AI
\`\`\`

## 4. Configure the application

\`\`\`bash
cp config/dag-nvr-ai.example.conf config/dag-nvr-ai.local.conf
\`\`\`

Edit the local file to match the NVR. The example contains the discovered NVR address and 13 allocated channels. Verify RTSP port and channel mapping before using those features.

Configuration precedence:

1. Built-in defaults.
2. Values in the selected config file.
3. Environment variables prefixed with \`DAG_\`.

NVR usernames and passwords are not accepted in tracked configuration. Supply them through environment variables:

\`\`\`bash
read -r -p "NVR username: " DAG_NVR_USERNAME
export DAG_NVR_USERNAME
read -r -s -p "NVR password: " DAG_NVR_PASSWORD
echo
export DAG_NVR_PASSWORD
\`\`\`

Do not paste credentials into source files, tracked config, logs or chat. Prefer a protected local environment file with restrictive permissions when running under systemd.

## 5. Validate configuration and application health

\`\`\`bash
cargo run --locked -- validate-config --config=config/dag-nvr-ai.local.conf
cargo run --locked -- health
cargo run --locked -- version
\`\`\`

The health command is a local process check; it does not test NVR connectivity.

## 6. Probe the NVR and listen for motion events

First verify Digest authentication and device identity:

\`\`\`bash
cargo run --locked -- probe-nvr --config=config/dag-nvr-ai.local.conf
\`\`\`

Then start the persistent alert stream:

\`\`\`bash
cargo run --locked -- listen-events --config=config/dag-nvr-ai.local.conf
\`\`\`

The listener emits structured log events for active VMD/video-motion events and reconnects after stream interruptions. Stop it with Ctrl+C or the service manager. The current implementation has not yet been validated against your physical NVR firmware; confirm event payloads, Digest compatibility and channel IDs before relying on alerts.

HTTP port 80 does not encrypt event contents. Keep the NVR and Jetson on a trusted isolated LAN; do not expose ISAPI or RTSP to the public Internet.

## 7. Run tests and build

\`\`\`bash
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --all-targets
cargo build --locked --release
\`\`\`

## Current scope

Version 0.3.4 provides Rust foundation, configuration validation, Digest-authenticated ISAPI device probing, persistent motion-event ingestion, bounded XML framing and structured logging. RTSP stream retrieval, SQLite persistence, AI inference, virtual fencing and Telegram notifications are subsequent features.

See the root [todo.md](../todo.md) for the implementation sequence and hardware acceptance checks.
