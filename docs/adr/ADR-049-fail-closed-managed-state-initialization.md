# ADR-049 — Fail-Closed Managed-State Initialization

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

Manager initialization previously reconciled selected transient task/step states. In a narrow case, it could refresh the integrity manifest after those rewrites and accept the resulting state. Task loading could also rewrite a task file when its UUID representation was normalizable.

These behaviors made ordinary startup and reads capable of changing authoritative state. They also risked treating an unexpected on-disk change as a recoverable normalization rather than a rejected mutation.

## Decision

- Loading task records is read-only. UUID normalization may occur in memory, but it must not rewrite the source record.
- Initialization validates an existing integrity manifest before creating missing workspace metadata.
- Initialization does not reconcile task/step lifecycle state.
- Initialization does not refresh an integrity manifest to accept detected changes.
- Task persistence rejects task-ID changes, duplicate IDs, and illegal lifecycle transitions before writing.
- Step persistence requires an existing owning task, preserves immutable step identity, validates the proposed complete step aggregate, and enforces the centralized step transition graph before writing.
- Integrity manifests are schema-checked before comparison: they must map safe relative paths to lowercase SHA-256 digests.
- Integrity mismatches are rejected and preserved for investigation.
- Explicit administrative repair is a separate future capability. It must require operator authorization and produce an auditable before/after record.
- Derived indexes and diagnostic telemetry are not authoritative workflow records; their write behavior must remain clearly separated from state mutations.

## Consequences

- Unexpected managed-state changes fail closed instead of being silently repaired.
- A damaged workspace may require an explicit administrative repair before normal operations can continue.
- This decision does not yet provide OS-level isolation against an agent process that can directly write the repository's managed directory. That requires an execution sandbox with the managed-state mount read-only.
- This decision does not yet make multi-file operations transactional. Those remain separate implementation work tracked in the repository root TODO.
- Regression tests cover read-only task loading, rejection of lifecycle tampering, and non-recreation of an integrity-protected deleted workspace record.
