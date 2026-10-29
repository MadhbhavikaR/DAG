# ADR-029: Make step readiness an explicit manager gate

## Status
Accepted

## Decision
Implementation steps use `ready` as the durable hand-off state after a validation failure and between sequential implementation steps. The manager promotes the current ready step to `active` when `manager next` selects that execution unit.

## Why
The specification defines the step lifecycle as `queued -> ready -> active -> implemented -> validating -> validated -> committing -> done` and requires later steps to remain queued until their predecessors are complete.

Making `ready` durable provides a restart-safe boundary between selecting the next bounded action and executing it. A failed validation therefore returns the step to `ready` rather than silently re-entering implementation without a new manager selection event.

## Consequences
- A validation failure is durably visible as `failed`, followed by a manager-owned `ready` recovery state.
- The next implementation step is `ready` until `manager next` promotes it.
- The manager remains the sole authority for `ready -> active`.
- Existing first-step activation remains compatible with the established protocol while subsequent/recovered steps use the explicit readiness gate.
