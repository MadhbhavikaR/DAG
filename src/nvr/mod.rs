//! Hikvision NVR integration.

pub mod client;
pub mod credentials;
pub mod curl_transport;
pub mod event;
pub mod framing;

use std::error::Error;
use std::fmt::{Display, Formatter};

/// NVR integration error with secret-safe messages.
#[derive(Debug)]
pub struct NvrError {
    message: String,
}

impl NvrError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for NvrError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for NvrError {}
