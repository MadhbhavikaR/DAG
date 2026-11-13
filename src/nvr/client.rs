//! Hikvision ISAPI device discovery and persistent motion-event listener.

use super::credentials::NvrCredentials;
use super::curl_transport::CurlTransport;
use super::event::{parse_device_info, parse_motion_event, DeviceInfo, MotionEvent};
use super::framing::EventFramer;
use super::NvrError;
use crate::config::Config;
use crate::config::LogLevel;
use crate::logging::log;
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub struct HikvisionIsapiClient {
    transport: CurlTransport,
}

impl HikvisionIsapiClient {
    pub fn new(config: &Config, credentials: NvrCredentials) -> Self {
        Self {
            transport: CurlTransport::new(
                config.curl_bin.clone(),
                config.nvr_host.clone(),
                config.nvr_http_port,
                credentials,
            ),
        }
    }

    pub fn probe(&self) -> Result<(String, DeviceInfo), NvrError> {
        let curl_version = self.transport.version()?;
        let response = self.transport.get_device_info()?;
        let device_info = parse_device_info(&response)?;
        Ok((curl_version, device_info))
    }

    /// Listen for active motion events, reconnecting with capped exponential backoff.
    pub fn listen<F>(&self, stop: &AtomicBool, mut on_event: F) -> Result<(), NvrError>
    where
        F: FnMut(MotionEvent),
    {
        if stop.load(Ordering::Acquire) {
            return Ok(());
        }

        let curl_version = self.transport.version()?;
        log(
            LogLevel::Info,
            &format!("starting Hikvision ISAPI listener with {curl_version}"),
        );

        let mut backoff_seconds = 1_u64;
        while !stop.load(Ordering::Acquire) {
            let mut connected = false;

            match self.transport.open_event_stream() {
                Ok(mut stream) => {
                    let mut framer = EventFramer::default();

                    loop {
                        if stop.load(Ordering::Acquire) {
                            stream.stop();
                            return Ok(());
                        }

                        match stream.recv_timeout(Duration::from_millis(500)) {
                            Ok(Some(chunk)) => {
                                connected = true;
                                backoff_seconds = 1;

                                let documents = match framer.push(&chunk) {
                                    Ok(documents) => documents,
                                    Err(_) => {
                                        log(
                                            LogLevel::Warn,
                                            "discarding oversized NVR event stream; reconnecting",
                                        );
                                        break;
                                    }
                                };

                                for document in documents {
                                    match parse_motion_event(&document) {
                                        Ok(Some(event)) => on_event(event),
                                        Ok(None) => {}
                                        Err(_) => log(
                                            LogLevel::Warn,
                                            "discarding malformed or unsupported NVR event XML",
                                        ),
                                    }
                                }
                            }
                            Ok(None) => {}
                            Err(_) => break,
                        }
                    }

                    stream.stop();
                }
                Err(error) => {
                    log(
                        LogLevel::Warn,
                        &format!("could not open NVR alertStream: {error}"),
                    );
                }
            }

            if stop.load(Ordering::Acquire) {
                break;
            }

            if connected {
                backoff_seconds = 1;
            } else {
                backoff_seconds = backoff_seconds.saturating_mul(2).min(60);
            }

            let jitter_ms = u64::from(
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .subsec_millis(),
            ) % 250;
            let mut remaining =
                Duration::from_secs(backoff_seconds) + Duration::from_millis(jitter_ms);
            while !stop.load(Ordering::Acquire) && !remaining.is_zero() {
                let interval = remaining.min(Duration::from_millis(250));
                thread::sleep(interval);
                remaining = remaining.saturating_sub(interval);
            }
        }

        Ok(())
    }
}
