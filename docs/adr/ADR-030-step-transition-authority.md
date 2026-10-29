# ADR-030: Manager-Owned Step Transition Authority

## Status
Accepted

## Context

The orchestration specification defines an explicit execution-unit lifecycle:

`queued -> ready -> active -> implemented -> validating -> validated -> committing -> done`

with failure and exception paths for blocked execution and validation recovery. A manager that mutates step status directly at multiple call sites can accidentally bypass that lifecycle, especially during restart recovery or future feature additions.

## Decision

The manager owns a single step-transition function and a canonical transition graph. Every durable step-state mutation must pass through that guard. The first planned step is created as `ready`; `manager next` promotes it to `active`. Validation failures pass through `failed` before returning to `ready`.

## Consequences

- Illegal step transitions fail before persistence with an actionable diagnostic.
- Step history remains reconstructable from managed records.
- `manager next` remains the explicit boundary at which ready implementation work becomes active work.
- Transient `implemented`, `validating`, `validated`, and `committing` states remain explicit and auditable.
- Recovery logic must use the same transition graph rather than assigning terminal states directly.
