# ADR-004: One bounded action per next response

## Decision
`manager next` returns exactly one executable action.

## Rationale
Small envelopes reduce context pressure and prevent a worker from skipping ahead.
