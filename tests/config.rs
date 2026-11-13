use dag_nvr_ai::config::{Config, LogLevel};

#[test]
fn defaults_are_safe_and_resource_bounded() {
    let config = Config::from_sources(None, Vec::<(String, String)>::new())
        .expect("default configuration should validate");

    assert_eq!(config.nvr_host, "127.0.0.1");
    assert_eq!(config.nvr_channels, 13);
    assert_eq!(config.event_queue_capacity, 128);
    assert_eq!(config.max_concurrent_inference, 1);
    assert_eq!(config.log_level, LogLevel::Info);
}

#[test]
fn environment_overrides_file_values() {
    let config = Config::from_sources(
        Some("NVR_HOST=192.168.100.103\nNVR_CHANNELS=13\nLOG_LEVEL=info\n"),
        vec![
            ("DAG_NVR_HOST".to_owned(), "nvr.local".to_owned()),
            ("DAG_NVR_CHANNELS".to_owned(), "12".to_owned()),
            ("DAG_LOG_LEVEL".to_owned(), "debug".to_owned()),
        ],
    )
    .expect("overridden configuration should validate");

    assert_eq!(config.nvr_host, "nvr.local");
    assert_eq!(config.nvr_channels, 12);
    assert_eq!(config.log_level, LogLevel::Debug);
}

#[test]
fn defaults_are_used_when_file_and_environment_omit_values() {
    let config = Config::from_sources(
        Some("NVR_HOST=192.168.100.103\n"),
        Vec::<(String, String)>::new(),
    )
    .expect("partial configuration should use defaults");

    assert_eq!(config.nvr_http_port, 80);
    assert_eq!(config.nvr_rtsp_port, 554);
    assert_eq!(config.event_queue_capacity, 128);
}

#[test]
fn rejects_unknown_configuration_keys() {
    let result = Config::from_sources(
        Some("NVR_HOST=localhost\nTYPO=bad\n"),
        Vec::<(String, String)>::new(),
    );

    assert!(result
        .unwrap_err()
        .to_string()
        .contains("unknown configuration key"));
}

#[test]
fn rejects_duplicate_configuration_keys() {
    let result = Config::from_sources(
        Some("NVR_HOST=localhost\nNVR_HOST=other\n"),
        Vec::<(String, String)>::new(),
    );

    assert!(result
        .unwrap_err()
        .to_string()
        .contains("duplicate configuration key"));
}

#[test]
fn rejects_malformed_configuration_lines() {
    let result = Config::from_sources(Some("NVR_HOST localhost\n"), Vec::<(String, String)>::new());

    assert!(result.unwrap_err().to_string().contains("KEY=VALUE"));
}

#[test]
fn rejects_invalid_ports_and_channel_counts() {
    for contents in [
        "NVR_HTTP_PORT=0\n",
        "NVR_CHANNELS=17\n",
        "NVR_CHANNELS=not-a-number\n",
    ] {
        assert!(Config::from_sources(Some(contents), Vec::<(String, String)>::new()).is_err());
    }
}

#[test]
fn rejects_unbounded_resource_settings() {
    for contents in [
        "EVENT_QUEUE_CAPACITY=0\n",
        "EVENT_QUEUE_CAPACITY=4097\n",
        "MAX_CONCURRENT_INFERENCE=3\n",
    ] {
        assert!(Config::from_sources(Some(contents), Vec::<(String, String)>::new()).is_err());
    }
}

#[test]
fn rejects_unknown_log_levels_and_empty_values() {
    for contents in ["LOG_LEVEL=trace\n", "NVR_HOST=\n"] {
        assert!(Config::from_sources(Some(contents), Vec::<(String, String)>::new()).is_err());
    }
}

#[test]
fn ignores_unrelated_environment_variables() {
    let config = Config::from_sources(None, vec![("HOME".to_owned(), "/tmp/user".to_owned())])
        .expect("unrelated environment variables must be ignored");

    assert_eq!(config.nvr_host, "127.0.0.1");
}


#[test]
fn curl_binary_is_configurable_from_file_and_environment() {
    let config = Config::from_sources(
        Some("CURL_BIN=/usr/bin/curl\n"),
        vec![("DAG_CURL_BIN".to_owned(), "/opt/bin/curl".to_owned())],
    )
    .expect("curl path should be configurable");

    assert_eq!(config.curl_bin, std::path::PathBuf::from("/opt/bin/curl"));
}

#[test]
fn rejects_url_injection_characters_in_nvr_host() {
    let result = Config::from_sources(
        Some("NVR_HOST=bad\\\"host\n"),
        Vec::<(String, String)>::new(),
    );

    assert!(result.is_err());
}
