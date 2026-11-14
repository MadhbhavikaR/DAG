# DAR-004: Camera channel inventory and RTSP URI analysis

**Status:** Reviewed; hardware assumptions remain open  
**Date:** 2026-11-14  
**Scope:** F-003 camera inventory and candidate RTSP endpoint generation

## Decision statement

How should the application represent the 13 NVR channels and derive stream endpoints while the physical camera allocation and exact NVR RTSP behavior remain unverified?

## Constraints and criteria

- Jetson Nano 4GB; avoid persistent per-camera decoder sessions.
- One configurable Rust process; no mandatory cloud service.
- No credentials in source, config maps, URI output or logs.
- Support 1–16 configured channels.
- Make unknown camera-to-channel relationships explicit.
- Keep work testable without access to the NVR.

## Options

| Option | Benefits | Costs and risks |
|---|---|---|
| Hard-code camera models and channel order | Simple initial configuration | Incorrect mapping risk; not supported by evidence |
| Probe every RTSP endpoint automatically | Could discover reachable channels | Requires credentials and protocol handling; can create load and leak secrets |
| Operator-maintained channel labels plus candidate URI generation | Deterministic, offline, bounded and auditable | Requires later manual hardware confirmation |

## Evidence and assumptions

**Known:** The NVR has 13 allocated channels. The physical mapping of the 11 Hikvision and 2 CP Plus cameras to those channels has not been captured.

**Assumption:** Hikvision NVR RTSP endpoints commonly use /Streaming/Channels/101 for channel 1 main stream and /Streaming/Channels/102 for channel 1 substream, with the channel number multiplied by 100 and a profile suffix.

**Unknown:** Exact URI behavior, port, authentication scheme, transport mode, codec and substream availability on firmware V4.83.010 build 241118.

## Comparative review

The operator-supplied mapping is the only option that avoids presenting guesses as facts. Offline URI generation is intentionally separated from network access. This preserves a future option to use GStreamer or another compatible media backend after validating JetPack 4.6.6 compatibility and secret handling.

## Recommendation and outcome

Accepted: implement strict channel labels and candidate main/substream URI generation. Do not implement RTSP scanning or decoding in this slice. Mark all hardware-dependent assumptions pending until tested on the actual NVR.

## Risks and mitigations

- **Wrong channel mapping:** generic labels by default; require operator confirmation.
- **Wrong URI convention:** label endpoints as candidates; no connectivity claims; hardware test before enabling stream access.
- **Credential leakage:** no credential fields or URL user-info support.
- **Resource exhaustion:** no sockets, decoders or media buffers are started by this feature.

## Review checklist

- [x] Strict map parser and channel bounds.
- [x] Main/substream URI builder.
- [x] Unit tests for malformed mappings and invalid authorities.
- [x] CLI inventory output and documentation.
- [ ] Confirm endpoint and profile suffixes on the target NVR.
- [ ] Verify RTSP authentication and TCP transport.
- [ ] Benchmark one substream on the Jetson Nano.

## Revisit triggers

Revisit when hardware validation reveals a different URI scheme, when stream access is implemented, or before choosing a media backend.
