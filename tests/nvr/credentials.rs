use dag_nvr_ai::nvr::credentials::NvrCredentials;

#[test]
fn debug_output_redacts_username_and_password() {
    let credentials =
        NvrCredentials::new("camera-admin", "private-password").expect("credentials are valid");
    let debug = format!("{credentials:?}");

    assert!(!debug.contains("camera-admin"));
    assert!(!debug.contains("private-password"));
    assert!(debug.contains("REDACTED"));
}

#[test]
fn rejects_unsafe_username_and_password_values() {
    assert!(NvrCredentials::new("user:name", "password").is_err());
    assert!(NvrCredentials::new("user\nname", "password").is_err());
    assert!(NvrCredentials::new("username", "pass\nword").is_err());
    assert!(NvrCredentials::new("username", "").is_err());
}
