//! Small JSON-lines logger using only the Rust standard library.

use crate::config::LogLevel;
use std::io::{self, Write};
use std::sync::atomic::{AtomicU8, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static MAX_LEVEL: AtomicU8 = AtomicU8::new(3);

/// Initialize the process-wide log threshold.
pub fn init(level: LogLevel) {
    MAX_LEVEL.store(level.as_number(), Ordering::Relaxed);
}

/// Emit one structured JSON log record to standard error.
pub fn log(level: LogLevel, message: &str) {
    if level.as_number() > MAX_LEVEL.load(Ordering::Relaxed) {
        return;
    }

    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let timestamp_ms = elapsed.as_millis();
    let level_name = level.as_str().to_ascii_uppercase();
    let escaped_message = escape_json_string(message);
    let mut stderr = io::stderr().lock();

    let _ = writeln!(
        stderr,
        "{{\"timestamp_unix_ms\":{timestamp_ms},\"level\":\"{level_name}\",\"message\":\"{escaped_message}\"}}"
    );
}

/// Escape a string for safe inclusion as a JSON string value.
pub fn escape_json_string(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());

    for character in value.chars() {
        match character {
            '"' => escaped.push_str("\\\""),
            '\\' => escaped.push_str("\\\\"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            character if character <= '\u{001f}' => {
                use std::fmt::Write as FmtWrite;
                let _ = write!(escaped, "\\u{:04x}", character as u32);
            }
            character => escaped.push(character),
        }
    }

    escaped
}
