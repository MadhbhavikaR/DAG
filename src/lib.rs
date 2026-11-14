//! Core library for the DAG Nano NVR AI application.

pub mod camera;
pub mod cli;
pub mod config;
pub mod logging;
pub mod nvr;

/// Version embedded from the Cargo package manifest.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
