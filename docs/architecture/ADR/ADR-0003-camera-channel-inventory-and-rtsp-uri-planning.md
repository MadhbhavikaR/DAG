# ADR-0003: Camera channel inventory and RTSP URI planning

**Status:** Accepted (URI format requires target-device validation)  
**Date:** 2026-11-14  
**Decision owners:** Project maintainers

## Context

F-003 needs a deterministic representation of NVR channels and stream profiles. The physical allocation of the 13 cameras is not yet confirmed. Camera labels must therefore remain operator-supplied metadata rather than inferred camera identities. The Jetson Nano has limited memory and decoder capacity, so this slice must not open all streams or create background decoder processes.

## Decision drivers

- Keep camera/channel mapping configurable and independent of hardware assumptions.
- Generate endpoints without embedding usernames or passwords.
- Keep the implementation dependency-free and suitable for ARM64.
- Do not start network sessions as a side effect of listing configuration.
- Keep channel and profile selection deterministic and bounded.

## Options considered

1. Hard-code the known camera models and assign them to NVR channels — rejected because the physical channel order is unknown.
2. Build a live RTSP scanner that probes every channel — rejected because it would require credentials, consume NVR/Jetson resources and could expose secrets or create load.
3. Maintain an optional operator-supplied channel label map and generate candidate main/substream URIs — accepted for this iteration.

## Decision

Implement a small camera registry with a strict CHANNEL_ID=LABEL file, generic labels for unmapped channels, and deterministic main/substream URI construction using the Hikvision NVR /Streaming/Channels/{channel}{profile} convention. Credentials are not included in URIs. The CLI only prints candidate endpoints; it does not connect, authenticate, decode or claim that the endpoints exist.

## Consequences

### Positive
- Channel metadata is explicit, reviewable and testable.
- No additional dependencies, threads, sockets or decoder sessions are introduced.
- Listing streams has constant bounded work proportional to the configured maximum of 16 channels.
- Secret material is not accepted by the camera-map parser or printed by this command.

### Negative and neutral
- The URI convention and stream suffixes remain assumptions until verified against the exact NVR firmware.
- A label is not proof of physical camera identity.
- This slice does not validate RTSP authentication, transport, codec support, frame rate or stream availability.

## Security and NFR implications

- Never put credentials in an RTSP URI, tracked file, process argument or log.
- Keep RTSP restricted to the trusted LAN.
- The command generates at most 32 candidate endpoints.
- No media buffers or decoders are allocated.
- Actual stream access must use a credential-safe transport and bounded session manager in a later feature.

## Validation and revisit triggers

- Unit tests cover path construction, IPv4/hostname/bracketed-IPv6 authorities, channel bounds, profile selection and invalid mappings.
- Hardware validation must confirm port, URI convention, channel numbering, Digest/basic authentication behavior and main/substream suffixes.
- Revisit this decision before adding a media backend or if the NVR uses a different URI convention.

## References

- Hikvision official integration center: https://tpp.hikvision.com/tpp/IntegrationCenter
- Hikvision NVR manuals and device-specific RTSP documentation must be checked for the exact DS-7616NXI-K1 firmware before enabling live access.
