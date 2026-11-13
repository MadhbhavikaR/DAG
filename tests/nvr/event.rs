use dag_nvr_ai::nvr::event::{parse_device_info, parse_motion_event};

const ACTIVE_MOTION: &str = r#"
<EventNotificationAlert version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ipAddress>192.168.100.103</ipAddress>
  <eventType>VMD</eventType>
  <eventState>active</eventState>
  <eventDescription>Video Motion</eventDescription>
  <channelID>4</channelID>
  <dateTime>2026-11-13T21:30:00+05:30</dateTime>
</EventNotificationAlert>
"#;

#[test]
fn parses_active_motion_event_with_default_xml_namespace() {
    let event = parse_motion_event(ACTIVE_MOTION.as_bytes())
        .expect("event XML should parse")
        .expect("active motion should be emitted");

    assert_eq!(event.channel_id, 4);
    assert_eq!(event.event_type, "VMD");
    assert_eq!(event.timestamp, "2026-11-13T21:30:00+05:30");
}

#[test]
fn ignores_inactive_motion_events() {
    let xml = ACTIVE_MOTION.replace(
        "<eventState>active</eventState>",
        "<eventState>inactive</eventState>",
    );
    assert!(parse_motion_event(xml.as_bytes())
        .expect("XML should parse")
        .is_none());
}

#[test]
fn ignores_non_motion_event_types() {
    let xml = ACTIVE_MOTION.replace(
        "<eventType>VMD</eventType>",
        "<eventType>videoloss</eventType>",
    );
    assert!(parse_motion_event(xml.as_bytes())
        .expect("XML should parse")
        .is_none());
}

#[test]
fn rejects_invalid_channel_numbers_for_motion_events() {
    let xml = ACTIVE_MOTION.replace("<channelID>4</channelID>", "<channelID>99</channelID>");
    assert!(parse_motion_event(xml.as_bytes()).is_err());
}

#[test]
fn rejects_malformed_xml() {
    assert!(parse_motion_event(b"<EventNotificationAlert").is_err());
}

#[test]
fn parses_nvr_device_identity() {
    let xml = br#"<DeviceInfo><deviceName>NVR</deviceName><model>DS-7616NXI-K1</model><firmwareVersion>V4.83.010</firmwareVersion><firmwareReleaseDate>241118</firmwareReleaseDate></DeviceInfo>"#;
    let device = parse_device_info(xml).expect("device info should parse");

    assert_eq!(device.model, "DS-7616NXI-K1");
    assert_eq!(device.firmware_version, "V4.83.010");
    assert_eq!(device.firmware_build, "241118");
}
