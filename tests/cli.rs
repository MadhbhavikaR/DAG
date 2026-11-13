use std::fs;
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_dag-nvr-ai")
}

fn temporary_path(prefix: &str) -> std::path::PathBuf {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock should be after epoch")
        .as_nanos();
    std::env::temp_dir().join(format!("{prefix}-{}-{unique}.conf", std::process::id()))
}

#[test]
fn health_command_reports_application_status() {
    let output = Command::new(binary())
        .arg("health")
        .output()
        .expect("binary should execute");

    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("stdout should be UTF-8");
    assert!(stdout.contains("\"status\":\"ok\""));
    assert!(stdout.contains("\"version\":\"0.3.0\""));
}

#[test]
fn validate_config_accepts_a_valid_file() {
    let path = temporary_path("dag-nvr-ai");
    fs::write(&path, "NVR_HOST=192.168.100.103\nNVR_CHANNELS=13\n")
        .expect("temporary config should be writable");

    let output = Command::new(binary())
        .arg("validate-config")
        .arg(format!("--config={}", path.display()))
        .output()
        .expect("binary should execute");
    let _ = fs::remove_file(&path);

    assert!(output.status.success());
    let stdout = String::from_utf8(output.stdout).expect("stdout should be UTF-8");
    assert!(stdout.contains("configuration valid"));
}

#[test]
fn validate_config_rejects_invalid_file() {
    let path = temporary_path("dag-nvr-ai-invalid");
    fs::write(&path, "NVR_CHANNELS=999\n").expect("temporary config should be writable");

    let output = Command::new(binary())
        .arg("validate-config")
        .arg(format!("--config={}", path.display()))
        .output()
        .expect("binary should execute");
    let _ = fs::remove_file(&path);

    assert!(!output.status.success());
}

#[test]
fn version_command_matches_package_metadata() {
    let output = Command::new(binary())
        .arg("version")
        .output()
        .expect("binary should execute");

    assert!(output.status.success());
    assert_eq!(
        String::from_utf8(output.stdout)
            .expect("stdout should be UTF-8")
            .trim(),
        "dag-nvr-ai 0.3.0"
    );
}
