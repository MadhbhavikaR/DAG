# ADR-037: Final-review corrections use monotonic identities and the manager readiness gate

## Decision

A corrective implementation step created from a failed final validation allocates its `STEP-####` identifier from the same per-task monotonic allocator used by normal planning, including archived plans. The correction is persisted as `ready`; `manager next` is the only operation that promotes it to `active`.

## Why

Final-review corrections are new durable execution records. Deriving their identifiers from the current plan length can collide with identifiers reserved by archived plans. Creating them directly as `active` would also bypass the manager-owned readiness boundary.

## Consequence

Restart and archival recovery preserve unique step identities, and every implementation action follows the same `ready -> active` manager selection boundary.
