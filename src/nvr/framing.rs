//! Bounded extraction of EventNotificationAlert XML documents from multipart streams.

use super::NvrError;

const OPEN_TAG: &[u8] = b"<EventNotificationAlert";
const CLOSE_TAG: &[u8] = b"</EventNotificationAlert>";
pub const MAX_EVENT_DOCUMENT_BYTES: usize = 256 * 1024;

/// Incremental event document framer with a strict memory bound.
#[derive(Default)]
pub struct EventFramer {
    buffer: Vec<u8>,
}

impl EventFramer {
    /// Add a stream chunk and return all complete event XML documents.
    pub fn push(&mut self, chunk: &[u8]) -> Result<Vec<Vec<u8>>, NvrError> {
        self.buffer.extend_from_slice(chunk);
        let mut documents = Vec::new();

        loop {
            let Some(start) = find_subslice(&self.buffer, OPEN_TAG) else {
                retain_possible_prefix(&mut self.buffer, OPEN_TAG);
                break;
            };

            if start > 0 {
                self.buffer.drain(..start);
            }

            if self.buffer.len() > MAX_EVENT_DOCUMENT_BYTES {
                self.buffer.clear();
                return Err(NvrError::new(
                    "NVR event XML exceeded the 256 KiB document limit",
                ));
            }

            let Some(end) = find_subslice(&self.buffer, CLOSE_TAG) else {
                break;
            };
            let document_end = end + CLOSE_TAG.len();
            documents.push(self.buffer[..document_end].to_vec());
            self.buffer.drain(..document_end);
        }

        if self.buffer.len() > MAX_EVENT_DOCUMENT_BYTES {
            self.buffer.clear();
            return Err(NvrError::new(
                "NVR event XML exceeded the 256 KiB document limit",
            ));
        }

        Ok(documents)
    }

    /// Discard incomplete trailing data when a connection closes.
    pub fn reset(&mut self) {
        self.buffer.clear();
    }
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

fn retain_possible_prefix(buffer: &mut Vec<u8>, marker: &[u8]) {
    let keep = marker.len().saturating_sub(1);
    if buffer.len() > keep {
        buffer.drain(..buffer.len() - keep);
    }
}
