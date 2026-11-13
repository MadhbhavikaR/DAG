use dag_nvr_ai::logging::escape_json_string;

#[test]
fn escapes_json_control_characters() {
    assert_eq!(
        escape_json_string("quote: \" slash: \\ line:\n tab:\t"),
        "quote: \\\" slash: \\\\ line:\\n tab:\\t"
    );
}

#[test]
fn preserves_unicode_and_escapes_control_bytes() {
    assert_eq!(escape_json_string("camera-ñ\u{0001}"), "camera-ñ\\u0001");
}
