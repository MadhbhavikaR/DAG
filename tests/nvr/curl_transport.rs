use dag_nvr_ai::nvr::credentials::NvrCredentials;
use dag_nvr_ai::nvr::curl_transport::CurlTransport;
use std::path::PathBuf;

#[test]
fn system_curl_version_can_be_inspected() {
    let credentials =
        NvrCredentials::new("integration-user", "not-a-real-password").expect("valid credentials");
    let transport = CurlTransport::new(
        PathBuf::from("curl"),
        "127.0.0.1".to_owned(),
        80,
        credentials,
    );

    let version = transport
        .version()
        .expect("GitHub Ubuntu runner should provide curl");
    assert!(version.starts_with("curl "));
}
