//! XML field extraction and normalized NVR event models.

use super::NvrError;
use quick_xml::events::Event as XmlEvent;
use quick_xml::Reader;
use std::collections::BTreeMap;

/// Normalized active motion event from the NVR.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MotionEvent {
    pub channel_id: u8,
    pub event_type: String,
    pub timestamp: String,
}

/// NVR identity and firmware information.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct DeviceInfo {
    pub model: String,
    pub firmware_version: String,
    pub firmware_build: String,
    pub device_name: String,
}

/// Parse the NVR device-info XML response.
pub fn parse_device_info(xml: &[u8]) -> Result<DeviceInfo, NvrError> {
    let fields = parse_xml_fields(xml)?;
    let model = required_field(&fields, "model")?;

    Ok(DeviceInfo {
        model,
        firmware_version: fields
            .get("firmwareversion")
            .cloned()
            .unwrap_or_else(|| "unknown".to_owned()),
        firmware_build: fields
            .get("firmwarereleasedate")
            .cloned()
            .unwrap_or_else(|| "unknown".to_owned()),
        device_name: fields
            .get("devicename")
            .cloned()
            .unwrap_or_else(|| "unknown".to_owned()),
    })
}

/// Parse one framed event XML document, returning only active motion events.
pub fn parse_motion_event(xml: &[u8]) -> Result<Option<MotionEvent>, NvrError> {
    let fields = parse_xml_fields(xml)?;
    let Some(event_type) = fields.get("eventtype") else {
        return Ok(None);
    };
    let Some(event_state) = fields.get("eventstate") else {
        return Ok(None);
    };

    let normalized_type = event_type.to_ascii_lowercase();
    if !matches!(
        normalized_type.as_str(),
        "vmd" | "videomotion" | "motion" | "motiondetection"
    ) {
        return Ok(None);
    }
    if !matches!(
        event_state.to_ascii_lowercase().as_str(),
        "active" | "activated"
    ) {
        return Ok(None);
    }

    let channel_text = required_field(&fields, "channelid")?;
    let channel_id = channel_text
        .parse::<u8>()
        .map_err(|_| NvrError::new("motion event contains an invalid channelID"))?;
    if !(1..=16).contains(&channel_id) {
        return Err(NvrError::new(
            "motion event channelID must be between 1 and 16",
        ));
    }

    let timestamp = required_field(&fields, "datetime")?;
    Ok(Some(MotionEvent {
        channel_id,
        event_type: event_type.clone(),
        timestamp,
    }))
}

fn required_field(fields: &BTreeMap<String, String>, name: &str) -> Result<String, NvrError> {
    fields
        .get(name)
        .filter(|value| !value.is_empty())
        .cloned()
        .ok_or_else(|| NvrError::new(format!("NVR XML is missing required field {name}")))
}

fn parse_xml_fields(xml: &[u8]) -> Result<BTreeMap<String, String>, NvrError> {
    let mut reader = Reader::from_reader(xml);
    reader.config_mut().trim_text(true);

    let mut buffer = Vec::new();
    let mut current_field: Option<String> = None;
    let mut fields = BTreeMap::new();

    loop {
        match reader.read_event_into(&mut buffer) {
            Ok(XmlEvent::Start(element)) => {
                current_field = Some(local_name(element.name().as_ref()));
            }
            Ok(XmlEvent::End(element)) => {
                let name = local_name(element.name().as_ref());
                if current_field.as_deref() == Some(name.as_str()) {
                    current_field = None;
                }
            }
            Ok(XmlEvent::Text(text)) => {
                if let Some(field) = current_field.as_ref() {
                    let value = text
                        .decode()
                        .map_err(|_| NvrError::new("NVR XML contains invalid text encoding"))?;
                    fields.entry(field.clone()).or_default().push_str(&value);
                }
            }
            Ok(XmlEvent::CData(text)) => {
                if let Some(field) = current_field.as_ref() {
                    let value = text
                        .decode()
                        .map_err(|_| NvrError::new("NVR XML contains invalid CDATA encoding"))?;
                    fields.entry(field.clone()).or_default().push_str(&value);
                }
            }
            Ok(XmlEvent::DocType(_)) => {
                return Err(NvrError::new("NVR XML document types are not accepted"));
            }
            Ok(XmlEvent::Eof) => break,
            Ok(_) => {}
            Err(_) => return Err(NvrError::new("NVR returned malformed XML")),
        }
        buffer.clear();
    }

    Ok(fields)
}

fn local_name(qualified_name: &[u8]) -> String {
    let local = qualified_name
        .rsplit(|byte| *byte == b':')
        .next()
        .unwrap_or(qualified_name);
    String::from_utf8_lossy(local).to_ascii_lowercase()
}
