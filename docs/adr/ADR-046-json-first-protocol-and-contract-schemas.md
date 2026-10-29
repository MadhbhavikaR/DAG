# ADR-046 — JSON-First Protocol and Contract Schemas

- **Status:** Accepted
- **Date:** 2026-10-04

## Context

The manager was originally consumed through human-readable envelopes and diagnostics. Weak/stateless agents and thin wrappers need deterministic parsing with low ambiguity and explicit contract validation.

## Decision

Adopt JSON as the runtime protocol default for command outputs and recoverable errors.

Define formal JSON schema artifacts under `docs/schemas/` for:

- `next`
- `context`
- `status`
- `status --compact`
- `submit-schema`
- `verify`
- `examples`
- `learn add`
- `learn list`
- error envelopes

Validate live command outputs against these schema files in automated tests.

## Consequences

- Integration runtimes can parse envelopes deterministically without text scraping.
- Contract drift is detected by tests tied to formal schemas.
- Backward text rendering is treated as compatibility/testing behavior, not protocol authority.
- Error recovery remains stable through `error/what/do` and optional bounded guidance fields.
