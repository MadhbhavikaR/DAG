use dag_nvr_ai::camera::{build_rtsp_uri, CameraRegistry, StreamProfile};

#[test]
fn builds_hikvision_nvr_main_and_substream_paths() {
    assert_eq!(
        build_rtsp_uri("192.168.100.103", 554, 1, StreamProfile::Main).unwrap(),
        "rtsp://192.168.100.103:554/Streaming/Channels/101"
    );
    assert_eq!(
        build_rtsp_uri("192.168.100.103", 554, 13, StreamProfile::Sub).unwrap(),
        "rtsp://192.168.100.103:554/Streaming/Channels/1302"
    );
}

#[test]
fn registry_uses_labels_and_fills_unmapped_channels() {
    let registry =
        CameraRegistry::from_mapping(Some("# test\n1=front_gate\n3=driveway\n"), 3).unwrap();

    assert_eq!(registry.channels()[0].label, "front_gate");
    assert_eq!(registry.channels()[1].label, "channel-02");
    assert_eq!(registry.channels()[2].label, "driveway");

    let streams = registry.streams("nvr.local", 554).unwrap();
    assert_eq!(streams.len(), 6);
    assert_eq!(streams[0].profile, StreamProfile::Main);
    assert_eq!(streams[1].profile, StreamProfile::Sub);
    assert!(streams[0].uri.ends_with("/101"));
    assert!(streams[1].uri.ends_with("/102"));
}

#[test]
fn rejects_duplicate_out_of_range_and_unsafe_mappings() {
    assert!(CameraRegistry::from_mapping(Some("1=front\n1=rear\n"), 2).is_err());
    assert!(CameraRegistry::from_mapping(Some("3=rear\n"), 2).is_err());
    assert!(CameraRegistry::from_mapping(Some("1=front gate\n"), 2).is_err());
    assert!(CameraRegistry::from_mapping(Some("1=front\nmalformed\n"), 2).is_err());
}

#[test]
fn rejects_invalid_rtsp_authority_and_channel() {
    assert!(build_rtsp_uri("nvr.local/path", 554, 1, StreamProfile::Main).is_err());
    assert!(build_rtsp_uri("nvr.local", 0, 1, StreamProfile::Main).is_err());
    assert!(build_rtsp_uri("nvr.local", 554, 0, StreamProfile::Main).is_err());
    assert!(build_rtsp_uri("nvr.local", 554, 17, StreamProfile::Main).is_err());
}

#[test]
fn supports_bracketed_ipv6_authority() {
    assert_eq!(
        build_rtsp_uri("[2001:db8::10]", 8554, 2, StreamProfile::Sub).unwrap(),
        "rtsp://[2001:db8::10]:8554/Streaming/Channels/202"
    );
}
