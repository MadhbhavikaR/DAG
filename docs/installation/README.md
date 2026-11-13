# Installation

## Jetson Nano

1. Confirm JetPack 4.6.6 / L4T 32.7.6, ARM64 architecture and available storage.
2. Install curl with Digest support: \`sudo apt-get install --no-install-recommends curl\`.
3. Verify curl using \`curl --version\` and test compatibility with the NVR's configured Digest algorithm.
4. Install the pinned Rust 1.100.0 toolchain using rustup.
5. Clone the repository and switch to \`DAG-Nano-4gb-NVR-AI\`.
6. Copy the example config to a local ignored config file.
7. Supply NVR credentials through protected environment variables or a protected systemd environment file.
8. Run \`cargo test --locked\` and \`cargo build --locked --release\`.
9. Validate configuration, then run \`probe-nvr\` before starting \`listen-events\`.

See [Quick Start](../QUICKSTART.md) for exact commands.

The application uses quick-xml for bounded XML parsing and system curl for HTTP Digest transport. The curl executable is an explicit runtime prerequisite. Future native integrations may require JetPack-provided GStreamer, CUDA and TensorRT development libraries. Those prerequisites will be added only with their respective feature and validated on the device.
