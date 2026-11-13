# Installation

## Jetson Nano

1. Confirm JetPack 4.6.6 / L4T 32.7.6, ARM64 architecture and available storage.
2. Install the pinned Rust 1.100.0 toolchain using rustup.
3. Clone the repository and switch to \`DAG-Nano-4gb-NVR-AI\`.
4. Copy the example config to a local ignored config file.
5. Run \`cargo test --locked\` and \`cargo build --locked --release\`.
6. Validate the config and local health command.

See [Quick Start](../QUICKSTART.md) for exact commands.

The Rust foundation currently uses only the standard library. Future native integrations may require JetPack-provided GStreamer, CUDA and TensorRT development libraries. Those prerequisites will be added only with their respective feature and validated on the device.
