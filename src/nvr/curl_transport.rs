//! Digest-authenticated HTTP transport backed by the system curl executable.

use super::credentials::NvrCredentials;
use super::NvrError;
use std::io::{self, Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::thread::{self, JoinHandle};
use std::time::Duration;

const MAX_DEVICE_INFO_BYTES: usize = 64 * 1024;
const STDERR_CAPTURE_BYTES: usize = 4096;
const STREAM_CHUNK_BYTES: usize = 8192;
const STREAM_QUEUE_CAPACITY: usize = 8;

/// HTTP transport for the NVR's ISAPI endpoints.
pub struct CurlTransport {
    binary: PathBuf,
    host: String,
    port: u16,
    credentials: NvrCredentials,
}

impl CurlTransport {
    /// Create a transport using a validated host/port and secret credentials.
    pub fn new(
        binary: PathBuf,
        host: String,
        port: u16,
        credentials: NvrCredentials,
    ) -> Self {
        Self {
            binary,
            host,
            port,
            credentials,
        }
    }

    /// Return the curl version for diagnostics and hardware compatibility checks.
    pub fn version(&self) -> Result<String, NvrError> {
        let output = Command::new(&self.binary)
            .arg("--version")
            .output()
            .map_err(|_| NvrError::new("curl executable was not found or could not be started"))?;

        if !output.status.success() {
            return Err(NvrError::new("curl --version returned a failure status"));
        }

        Ok(String::from_utf8_lossy(&output.stdout)
            .lines()
            .next()
            .unwrap_or("curl version unavailable")
            .to_owned())
    }

    /// Fetch a small XML response with a strict response-size limit.
    pub fn get_device_info(&self) -> Result<Vec<u8>, NvrError> {
        let mut child = self.spawn_request("/ISAPI/System/deviceInfo", 10)?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| NvrError::new("curl stdout pipe was unavailable"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| NvrError::new("curl stderr pipe was unavailable"))?;
        let stderr_reader = thread::spawn(move || drain_stderr(stderr));

        let mut body = Vec::new();
        let read_result = stdout
            .take((MAX_DEVICE_INFO_BYTES + 1) as u64)
            .read_to_end(&mut body);

        if read_result.is_err() {
            let _ = child.kill();
            let _ = child.wait();
            let _ = stderr_reader.join();
            return Err(NvrError::new("failed while reading NVR device-info response"));
        }

        if body.len() > MAX_DEVICE_INFO_BYTES {
            let _ = child.kill();
            let _ = child.wait();
            let _ = stderr_reader.join();
            return Err(NvrError::new(
                "NVR device-info response exceeded the 64 KiB limit",
            ));
        }

        let status = child
            .wait()
            .map_err(|_| NvrError::new("could not collect curl process status"))?;
        let _ = stderr_reader.join();

        if !status.success() {
            return Err(NvrError::new(
                "curl device-info request failed; check NVR reachability and Digest credentials",
            ));
        }

        Ok(body)
    }

    /// Open a persistent alertStream request and expose bounded stdout chunks.
    pub fn open_event_stream(&self) -> Result<AlertStream, NvrError> {
        let mut child = self.spawn_request("/ISAPI/Event/notification/alertStream", 0)?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| NvrError::new("curl stdout pipe was unavailable"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| NvrError::new("curl stderr pipe was unavailable"))?;

        let (sender, receiver) = mpsc::sync_channel(STREAM_QUEUE_CAPACITY);
        let reader = thread::spawn(move || {
            let mut stdout = stdout;
            loop {
                let mut chunk = vec![0_u8; STREAM_CHUNK_BYTES];
                match stdout.read(&mut chunk) {
                    Ok(0) | Err(_) => break,
                    Ok(length) => {
                        chunk.truncate(length);
                        if sender.send(chunk).is_err() {
                            break;
                        }
                    }
                }
            }
        });
        let stderr_reader = thread::spawn(move || drain_stderr(stderr));

        Ok(AlertStream {
            child,
            receiver: Some(receiver),
            reader: Some(reader),
            stderr_reader: Some(stderr_reader),
        })
    }

    fn spawn_request(&self, path: &str, max_time_seconds: u64) -> Result<Child, NvrError> {
        let mut config = self.build_curl_config(path, max_time_seconds)?;
        let spawn_result = Command::new(&self.binary)
            // -q must be the first curl option: do not load a user's curlrc.
            .arg("-q")
            .arg("--config")
            .arg("-")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn();

        let mut child = match spawn_result {
            Ok(child) => child,
            Err(_) => {
                config.fill(0);
                return Err(NvrError::new(
                    "could not start curl; install curl and verify CURL_BIN",
                ));
            }
        };

        let write_result = match child.stdin.take() {
            Some(mut stdin) => stdin.write_all(&config),
            None => Err(io::Error::other("curl stdin pipe was unavailable")),
        };
        config.fill(0);

        if write_result.is_err() {
            let _ = child.kill();
            let _ = child.wait();
            return Err(NvrError::new("could not provide curl request configuration"));
        }

        Ok(child)
    }

    fn build_curl_config(
        &self,
        path: &str,
        max_time_seconds: u64,
    ) -> Result<Vec<u8>, NvrError> {
        let url = format!("http://{}:{}{}", self.host, self.port, path);
        let user_pass_length =
            self.credentials.username().len() + 1 + self.credentials.password().len();
        let mut user_pass = Vec::with_capacity(user_pass_length);
        user_pass.extend_from_slice(self.credentials.username().as_bytes());
        user_pass.push(b':');
        user_pass.extend_from_slice(self.credentials.password().as_bytes());

        let mut config = Vec::with_capacity(url.len() + user_pass.len() + 192);
        append_quoted_option(&mut config, "url", url.as_bytes())?;
        let user_result = append_quoted_option(&mut config, "user", &user_pass);
        user_pass.fill(0);
        user_result?;

        config.extend_from_slice(
            b"digest\nsilent\nshow-error\nno-buffer\nfail\nconnect-timeout = 10\n",
        );
        config.extend_from_slice(format!("max-time = {max_time_seconds}\n").as_bytes());
        config.extend_from_slice(
            b"noproxy = \"*\"\nheader = \"Accept: application/xml\"\nproto = \"=http\"\n",
        );
        Ok(config)
    }
}

/// Persistent curl process and bounded stream receiver.
pub struct AlertStream {
    child: Child,
    receiver: Option<Receiver<Vec<u8>>>,
    reader: Option<JoinHandle<()>>,
    stderr_reader: Option<JoinHandle<Vec<u8>>>,
}

impl AlertStream {
    /// Wait briefly for the next body chunk; timeout is not a stream failure.
    pub fn recv_timeout(&self, timeout: Duration) -> Result<Option<Vec<u8>>, NvrError> {
        let receiver = self
            .receiver
            .as_ref()
            .ok_or_else(|| NvrError::new("alert stream has already stopped"))?;

        match receiver.recv_timeout(timeout) {
            Ok(chunk) => Ok(Some(chunk)),
            Err(RecvTimeoutError::Timeout) => Ok(None),
            Err(RecvTimeoutError::Disconnected) => {
                Err(NvrError::new("NVR alertStream connection ended"))
            }
        }
    }

    /// Stop the child and join its bounded pipe-reader threads.
    pub fn stop(&mut self) {
        self.receiver.take();
        let _ = self.child.kill();
        let _ = self.child.wait();

        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
        }
        if let Some(stderr_reader) = self.stderr_reader.take() {
            let _ = stderr_reader.join();
        }
    }
}

impl Drop for AlertStream {
    fn drop(&mut self) {
        self.stop();
    }
}

fn append_quoted_option(
    output: &mut Vec<u8>,
    name: &str,
    value: &[u8],
) -> Result<(), NvrError> {
    if value.iter().any(|byte| *byte < 0x20 || *byte == 0x7f) {
        return Err(NvrError::new(
            "curl config values must not contain control characters",
        ));
    }

    output.extend_from_slice(name.as_bytes());
    output.extend_from_slice(b" = \"");
    for byte in value {
        match byte {
            b'"' => output.extend_from_slice(b"\\\""),
            b'\\' => output.extend_from_slice(b"\\\\"),
            value => output.push(*value),
        }
    }
    output.extend_from_slice(b"\"\n");
    Ok(())
}

fn drain_stderr<R: Read>(mut reader: R) -> Vec<u8> {
    let mut retained = Vec::with_capacity(STDERR_CAPTURE_BYTES);
    let mut buffer = [0_u8; 1024];

    loop {
        match reader.read(&mut buffer) {
            Ok(0) | Err(_) => break,
            Ok(length) => {
                let remaining = STDERR_CAPTURE_BYTES.saturating_sub(retained.len());
                retained.extend_from_slice(&buffer[..length.min(remaining)]);
            }
        }
    }

    retained
}

#[cfg(test)]
mod tests {
    use super::append_quoted_option;

    #[test]
    fn curl_config_escapes_quotes_and_backslashes() {
        let mut output = Vec::new();
        append_quoted_option(&mut output, "user", b"user:pa\\\"ss")
            .expect("safe values should be quoted");
        assert_eq!(
            String::from_utf8(output).expect("config should be UTF-8"),
            "user = \"user:pa\\\\\\\"ss\"\n"
        );
    }

    #[test]
    fn curl_config_rejects_control_characters() {
        let mut output = Vec::new();
        assert!(append_quoted_option(&mut output, "user", b"user:pass\n").is_err());
    }
}
