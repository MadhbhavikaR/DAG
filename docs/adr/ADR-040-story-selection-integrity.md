# ADR-040: Story Selection Integrity

## Decision

Story activity scope is validated as a persisted-state invariant in addition to manager-owned task allocation.

Multiple stories may coexist, but only one story may own active lifecycle states (`active`, `expand`, or `blocked`) at a time. Startup therefore fails closed if managed records are modified such that active lifecycle ownership spans multiple stories.

## Rationale

Selection must remain deterministic after restart even when multiple stories are present. Allocation rules alone are insufficient because managed files are durable state and may be corrupted or manually modified. Story-scoped execution ownership ensures `manager next` cannot silently interleave work across stories.

## Consequence

A malformed workspace that contains active lifecycle state in more than one story requires administrative repair before mutation can continue. Later-story task creation remains supported.
