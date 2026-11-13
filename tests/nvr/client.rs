use dag_nvr_ai::config::Config;
use dag_nvr_ai::nvr::client::HikvisionIsapiClient;
use dag_nvr_ai::nvr::credentials::NvrCredentials;
use std::sync::atomic::AtomicBool;

#[test]
fn already_cancelled_listener_does_not_start_network_io() {
    let config = Config::default();
    let credentials =
        NvrCredentials::new("integration-user", "not-a-real-password").expect("valid credentials");
    let client = HikvisionIsapiClient::new(&config, credentials);
    let stop = AtomicBool::new(true);

    client
        .listen(&stop, |_| panic!("cancelled listener must not emit events"))
        .expect("already-cancelled listener should exit cleanly");
}
