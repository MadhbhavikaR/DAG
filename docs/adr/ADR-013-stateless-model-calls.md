# ADR-013: Stateless model calls

## Decision
Every execution envelope is sufficient without conversation memory.

## Rationale
Models may restart, truncate context, or be replaced.
