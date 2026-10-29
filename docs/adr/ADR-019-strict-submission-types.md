# ADR-019: Enforce strict structured submission types

**Status:** Accepted

## Decision

Phase submissions must validate container element types explicitly rather than coercing arbitrary JSON values to strings.

## Why

The protocol defines JSON schemas, not stringly typed payloads. Silent coercion can turn malformed model output into valid-looking workflow records and weakens the manager's mutation boundary.

## Consequences

- IDs, paths, commands, and list fields reject non-string members.
- Validation results reject duplicate command entries.
- The manager returns `ERROR`, `WHAT`, and `DO` instead of coercing malformed content.
- Existing valid submissions remain unchanged.
