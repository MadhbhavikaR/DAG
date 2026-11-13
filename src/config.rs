//! Strict, dependency-free application configuration.

use std::collections::BTreeMap;
use std::env;
use std::error::Error;
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LogLevel {
    Error,
    Warn,
    Info,
    Debug,
}

impl LogLevel {
    pub fn parse(value: &str) -> Result<Self, ConfigError> {
        match value.to_ascii_lowercase().as_str() {
            "error" => Ok(Self::Error),
            "warn" | "warning" => Ok(Self::Warn),
            "info" => Ok(Self::Info),
            "debug" => Ok(Self::Debug),
            _ => Err(ConfigError::new(
                "LOG_LEVEL must be one of: error, warn, info, debug",
            )),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Error => "error",
            Self::Warn => "warn",
            Self::Info => "info",
            Self::Debug => "debug",
        }
    }

    pub(crate) fn as_number(self) -> u8 {
        match self {
            Self::Error => 1,
            Self::Warn => 2,
            Self::Info => 3,
            Self::Debug => 4,
        }
    }
}

/// Validated runtime configuration. Secrets are deliberately excluded.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Config {
    pub nvr_host: String,
    pub nvr_http_port: u16,
    pub nvr_rtsp_port: u16,
    pub nvr_channels: u8,
    pub curl_bin: PathBuf,
    pub event_queue_capacity: usize,
    pub max_concurrent_inference: usize,
    pub log_level: LogLevel,
    pub data_dir: PathBuf,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ConfigError {
    message: String,
}

impl ConfigError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for ConfigError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for ConfigError {}

impl Default for Config {
    fn default() -> Self {
        Self {
            nvr_host: "127.0.0.1".to_owned(),
            nvr_http_port: 80,
            nvr_rtsp_port: 554,
            nvr_channels: 13,
            curl_bin: PathBuf::from("curl"),
            event_queue_capacity: 128,
            max_concurrent_inference: 1,
            log_level: LogLevel::Info,
            data_dir: PathBuf::from("runtime"),
        }
    }
}

impl Config {
    /// Load defaults, an optional file, then DAG_* environment overrides.
    pub fn load(path: Option<&Path>) -> Result<Self, ConfigError> {
        let contents = match path {
            Some(config_path) => Some(fs::read_to_string(config_path).map_err(|error| {
                ConfigError::new(format!(
                    "cannot read configuration file {}: {error}",
                    config_path.display()
                ))
            })?),
            None => {
                let default_path = Path::new("config/dag-nvr-ai.local.conf");
                if default_path.is_file() {
                    Some(fs::read_to_string(default_path).map_err(|error| {
                        ConfigError::new(format!("cannot read default configuration file: {error}"))
                    })?)
                } else {
                    None
                }
            }
        };

        Self::from_sources(contents.as_deref(), env::vars())
    }

    /// Build configuration from file text and injected environment pairs.
    pub fn from_sources<I, K, V>(
        file_contents: Option<&str>,
        environment: I,
    ) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = (K, V)>,
        K: AsRef<str>,
        V: AsRef<str>,
    {
        let mut values = BTreeMap::new();
        if let Some(contents) = file_contents {
            for (key, value) in parse_config_file(contents)? {
                values.insert(key, value);
            }
        }

        for (name, value) in environment {
            if let Some(key) = environment_key(name.as_ref()) {
                values.insert(key.to_owned(), value.as_ref().trim().to_owned());
            }
        }

        Self::from_values(values)
    }

    fn from_values(values: BTreeMap<String, String>) -> Result<Self, ConfigError> {
        let defaults = Self::default();
        let config = Self {
            nvr_host: string_value(&values, "NVR_HOST")
                .unwrap_or_else(|| defaults.nvr_host.clone()),
            nvr_http_port: number_value(&values, "NVR_HTTP_PORT", defaults.nvr_http_port)?,
            nvr_rtsp_port: number_value(&values, "NVR_RTSP_PORT", defaults.nvr_rtsp_port)?,
            nvr_channels: number_value(&values, "NVR_CHANNELS", defaults.nvr_channels)?,
            curl_bin: string_value(&values, "CURL_BIN")
                .map(PathBuf::from)
                .unwrap_or(defaults.curl_bin),
            event_queue_capacity: number_value(
                &values,
                "EVENT_QUEUE_CAPACITY",
                defaults.event_queue_capacity,
            )?,
            max_concurrent_inference: number_value(
                &values,
                "MAX_CONCURRENT_INFERENCE",
                defaults.max_concurrent_inference,
            )?,
            log_level: match string_value(&values, "LOG_LEVEL") {
                Some(value) => LogLevel::parse(&value)?,
                None => defaults.log_level,
            },
            data_dir: string_value(&values, "DATA_DIR")
                .map(PathBuf::from)
                .unwrap_or(defaults.data_dir),
        };

        config.validate()?;
        Ok(config)
    }

    pub fn validate(&self) -> Result<(), ConfigError> {
        if self.nvr_host.is_empty()
            || self.nvr_host.len() > 253
            || !self.nvr_host.chars().all(|character| {
                character.is_ascii_alphanumeric() || ".-:[]".contains(character)
            })
        {
            return Err(ConfigError::new(
                "NVR_HOST must be a hostname, IPv4 address or bracketed IPv6 address",
            ));
        }
        if self.nvr_http_port == 0 || self.nvr_rtsp_port == 0 {
            return Err(ConfigError::new("NVR ports must be between 1 and 65535"));
        }
        if !(1..=16).contains(&self.nvr_channels) {
            return Err(ConfigError::new("NVR_CHANNELS must be between 1 and 16"));
        }
        if self.curl_bin.as_os_str().is_empty() {
            return Err(ConfigError::new("CURL_BIN must not be empty"));
        }
        if !(1..=4096).contains(&self.event_queue_capacity) {
            return Err(ConfigError::new(
                "EVENT_QUEUE_CAPACITY must be between 1 and 4096",
            ));
        }
        if !(1..=2).contains(&self.max_concurrent_inference) {
            return Err(ConfigError::new(
                "MAX_CONCURRENT_INFERENCE must be 1 or 2 on the Jetson Nano target",
            ));
        }
        if self.data_dir.as_os_str().is_empty() {
            return Err(ConfigError::new("DATA_DIR must not be empty"));
        }
        Ok(())
    }
}

fn parse_config_file(contents: &str) -> Result<BTreeMap<String, String>, ConfigError> {
    let mut values = BTreeMap::new();

    for (index, raw_line) in contents.lines().enumerate() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }

        let (raw_key, raw_value) = line.split_once('=').ok_or_else(|| {
            ConfigError::new(format!(
                "configuration line {} must use KEY=VALUE syntax",
                index + 1
            ))
        })?;
        let key = raw_key.trim();
        let value = raw_value.trim();

        if !is_supported_key(key) {
            return Err(ConfigError::new(format!(
                "unknown configuration key on line {}: {key}",
                index + 1
            )));
        }
        if value.is_empty() {
            return Err(ConfigError::new(format!(
                "configuration value for {key} on line {} is empty",
                index + 1
            )));
        }
        if values.insert(key.to_owned(), value.to_owned()).is_some() {
            return Err(ConfigError::new(format!(
                "duplicate configuration key on line {}: {key}",
                index + 1
            )));
        }
    }

    Ok(values)
}

fn is_supported_key(key: &str) -> bool {
    matches!(
        key,
        "NVR_HOST"
            | "NVR_HTTP_PORT"
            | "NVR_RTSP_PORT"
            | "NVR_CHANNELS"
            | "CURL_BIN"
            | "EVENT_QUEUE_CAPACITY"
            | "MAX_CONCURRENT_INFERENCE"
            | "LOG_LEVEL"
            | "DATA_DIR"
    )
}

fn environment_key(name: &str) -> Option<&'static str> {
    match name {
        "DAG_NVR_HOST" => Some("NVR_HOST"),
        "DAG_NVR_HTTP_PORT" => Some("NVR_HTTP_PORT"),
        "DAG_NVR_RTSP_PORT" => Some("NVR_RTSP_PORT"),
        "DAG_NVR_CHANNELS" => Some("NVR_CHANNELS"),
        "DAG_CURL_BIN" => Some("CURL_BIN"),
        "DAG_EVENT_QUEUE_CAPACITY" => Some("EVENT_QUEUE_CAPACITY"),
        "DAG_MAX_CONCURRENT_INFERENCE" => Some("MAX_CONCURRENT_INFERENCE"),
        "DAG_LOG_LEVEL" => Some("LOG_LEVEL"),
        "DAG_DATA_DIR" => Some("DATA_DIR"),
        _ => None,
    }
}

fn string_value(values: &BTreeMap<String, String>, key: &str) -> Option<String> {
    values.get(key).cloned()
}

fn number_value<T>(
    values: &BTreeMap<String, String>,
    key: &str,
    default: T,
) -> Result<T, ConfigError>
where
    T: std::str::FromStr,
{
    match values.get(key) {
        Some(value) => value.parse::<T>().map_err(|_| {
            ConfigError::new(format!(
                "configuration value for {key} is not a valid number"
            ))
        }),
        None => Ok(default),
    }
}
