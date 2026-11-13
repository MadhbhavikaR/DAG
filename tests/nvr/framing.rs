use dag_nvr_ai::nvr::framing::{EventFramer, MAX_EVENT_DOCUMENT_BYTES};

const EVENT: &[u8] = b"<EventNotificationAlert><eventType>VMD</eventType></EventNotificationAlert>";

#[test]
fn extracts_event_split_across_stream_chunks() {
    let mut framer = EventFramer::default();
    assert!(framer.push(&EVENT[..17]).expect("first chunk is valid").is_empty());

    let documents = framer.push(&EVENT[17..]).expect("second chunk completes XML");
    assert_eq!(documents, vec![EVENT.to_vec()]);
}

#[test]
fn extracts_multiple_events_and_discards_multipart_noise() {
    let mut framer = EventFramer::default();
    let mut input = b"--boundary\r\nContent-Type: application/xml\r\n\r\n".to_vec();
    input.extend_from_slice(EVENT);
    input.extend_from_slice(b"\r\n--boundary\r\n");
    input.extend_from_slice(EVENT);

    let documents = framer.push(&input).expect("multipart data should be framed");
    assert_eq!(documents, vec![EVENT.to_vec(), EVENT.to_vec()]);
}

#[test]
fn rejects_oversized_incomplete_event() {
    let mut framer = EventFramer::default();
    let mut input = b"<EventNotificationAlert>".to_vec();
    input.resize(MAX_EVENT_DOCUMENT_BYTES + 1, b'x');

    assert!(framer.push(&input).is_err());
}

#[test]
fn ignores_noise_without_growing_buffer() {
    let mut framer = EventFramer::default();
    let noise = vec![b'x'; MAX_EVENT_DOCUMENT_BYTES + 100];
    assert!(framer.push(&noise).expect("noise should be discarded").is_empty());
}
