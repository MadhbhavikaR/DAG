//! Camera channel inventory and deterministic RTSP URI planning.
//!
//! This module does not open network sessions. It keeps camera labels separate
//! from NVR channel numbers because physical channel allocation must be verified.

use std::collections::BTreeMap;
use std::error::Error;
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::Path;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum StreamProfile {
    Main,
    Sub,
}

impl StreamProfile {
    pub fn channel_suffix(self) -> u8 {
        match self {
            Self::Main => 1,
            Self::Sub => 2,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Main => "main",
            Self::Sub => "sub",
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CameraChannel {
    pub channel_id: u8,
    pub label: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RtspStream {
    pub channel_id: u8,
    pub camera_label: String,
    pub profile: StreamProfile,
    pub uri: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CameraRegistry {
    channels: Vec<CameraChannel>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CameraError {
    message: String,
}

impl CameraError {
    fn new(message: impl Into<String>) -> Self {
        Self { message: message.into() }
    }
}

impl Display for CameraError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for CameraError {}

impl CameraRegistry {
    /// Load optional channel labels. Unmapped channels retain stable generic labels.
    pub fn load(path: Option<&Path>, channel_count: u8) -> Result<Self, CameraError> {
        let contents = match path {
            Some(path) => Some(fs::read_to_string(path).map_err(|error| {
                CameraError::new(format!("cannot read camera map {}: {error}", path.display()))
            })?),
            None => None,
        };
        Self::from_mapping(contents.as_deref(), channel_count)
    }

    pub fn from_mapping(contents: Option<&str>, channel_count: u8) -> Result<Self, CameraError> {
        if !(1..=16).contains(&channel_count) {
            return Err(CameraError::new("camera channel count must be between 1 and 16"));
        }

        let mut labels = BTreeMap::new();
        if let Some(contents) = contents {
            for (index, raw_line) in contents.lines().enumerate() {
                let line = raw_line.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                let (raw_channel, raw_label) = line.split_once('=').ok_or_else(|| {
                    CameraError::new(format!(
                        "camera map line {} must use CHANNEL_ID=LABEL syntax",
                        index + 1
                    ))
                })?;
                let channel_id = raw_channel.trim().parse::<u8>().map_err(|_| {
                    CameraError::new(format!("invalid channel ID on camera map line {}", index + 1))
                })?;
                if channel_id == 0 || channel_id > channel_count {
                    return Err(CameraError::new(format!(
                        "camera map channel {channel_id} is outside configured range 1..={channel_count}"
                    )));
                }
                let label = raw_label.trim();
                if !valid_label(label) {
                    return Err(CameraError::new(format!(
                        "invalid camera label on line {}: use 1-48 ASCII letters, digits, '-' or '_'",
                        index + 1
                    )));
                }
                if labels.insert(channel_id, label.to_owned()).is_some() {
                    return Err(CameraError::new(format!(
                        "duplicate camera channel mapping on line {}: {channel_id}",
                        index + 1
                    )));
                }
            }
        }

        let channels = (1..=channel_count)
            .map(|channel_id| CameraChannel {
                channel_id,
                label: labels
                    .remove(&channel_id)
                    .unwrap_or_else(|| format!("channel-{channel_id:02}")),
            })
            .collect();

        Ok(Self { channels })
    }

    pub fn channels(&self) -> &[CameraChannel] {
        &self.channels
    }

    /// Plan main and substream RTSP endpoints without embedding credentials.
    pub fn streams(&self, host: &str, port: u16) -> Result<Vec<RtspStream>, CameraError> {
        validate_rtsp_authority(host, port)?;
        let mut streams = Vec::with_capacity(self.channels.len() * 2);
        for camera in &self.channels {
            for profile in [StreamProfile::Main, StreamProfile::Sub] {
                streams.push(RtspStream {
                    channel_id: camera.channel_id,
                    camera_label: camera.label.clone(),
                    profile,
                    uri: build_rtsp_uri(host, port, camera.channel_id, profile)?,
                });
            }
        }
        Ok(streams)
    }
}

pub fn build_rtsp_uri(
    host: &str,
    port: u16,
    channel_id: u8,
    profile: StreamProfile,
) -> Result<String, CameraError> {
    validate_rtsp_authority(host, port)?;
    if !(1..=16).contains(&channel_id) {
        return Err(CameraError::new("RTSP channel ID must be between 1 and 16"));
    }
    let stream_number = u16::from(channel_id) * 100 + u16::from(profile.channel_suffix());
    Ok(format!("rtsp://{host}:{port}/Streaming/Channels/{stream_number}"))
}

fn validate_rtsp_authority(host: &str, port: u16) -> Result<(), CameraError> {
    if host.is_empty()
        || host.len() > 253
        || host.chars().any(|character| {
            character.is_whitespace() || "/@?#".contains(character)
        })
    {
        return Err(CameraError::new(
            "RTSP host must be a hostname, IPv4 address or bracketed IPv6 address without URI components",
        ));
    }
    if port == 0 {
        return Err(CameraError::new("RTSP port must be between 1 and 65535"));
    }
    Ok(())
}

fn valid_label(label: &str) -> bool {
    !label.is_empty()
        && label.len() <= 48
        && label
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || "-_".contains(character))
}
