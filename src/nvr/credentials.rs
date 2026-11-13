//! Environment-sourced NVR credentials with redacted diagnostics.

use super::NvrError;
use std::env;
use std::fmt::{Debug, Formatter};

/// NVR credentials. Values are never included in Debug output.
pub struct NvrCredentials {
    username: Vec<u8>,
    password: Vec<u8>,
}

impl NvrCredentials {
    /// Construct credentials after validating curl config constraints.
    pub fn new(username: &str, password: &str) -> Result<Self, NvrError> {
        if username.is_empty()
            || username.contains(':')
            || username.chars().any(char::is_control)
        {
            return Err(NvrError::new(
                "NVR username must be non-empty and must not contain ':' or control characters",
            ));
        }
        if password.is_empty() || password.chars().any(char::is_control) {
            return Err(NvrError::new(
                "NVR password must be non-empty and must not contain control characters",
            ));
        }

        Ok(Self {
            username: username.as_bytes().to_vec(),
            password: password.as_bytes().to_vec(),
        })
    }

    /// Read credentials from protected environment variables.
    pub fn from_env() -> Result<Self, NvrError> {
        let username = env::var("DAG_NVR_USERNAME")
            .map_err(|_| NvrError::new("DAG_NVR_USERNAME environment variable is required"))?;
        let password = env::var("DAG_NVR_PASSWORD")
            .map_err(|_| NvrError::new("DAG_NVR_PASSWORD environment variable is required"))?;

        Self::new(&username, &password)
    }

    pub(crate) fn username(&self) -> &str {
        std::str::from_utf8(&self.username).expect("validated UTF-8 username")
    }

    pub(crate) fn password(&self) -> &str {
        std::str::from_utf8(&self.password).expect("validated UTF-8 password")
    }
}

impl Debug for NvrCredentials {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter
            .debug_struct("NvrCredentials")
            .field("username", &"[REDACTED]")
            .field("password", &"[REDACTED]")
            .finish()
    }
}

impl Drop for NvrCredentials {
    fn drop(&mut self) {
        self.username.fill(0);
        self.password.fill(0);
    }
}
