# ADR-036: Enforce Monotonic Step Identifiers at Every Plan Entry Point

**Status:** Accepted

## Decision

Every manager-owned plan submission allocates implementation-step identifiers from the task's durable monotonic step counter. Plan-local sequence numbers may restart at `1`, but `STEP-####` record identities never restart or reuse an archived identifier.

## Why

The specification defines record IDs as durable identities that are never reused within a task. A replanning path that allocates `STEP-0001` again would make historical evidence ambiguous and could cause restart reconstruction to associate a current execution unit with an archived record.

## Consequence

All plan submission entry points use the same `next_step_number()` allocation rule. Tests must exercise both the normal `manager submit` planning path and the explicit `manager plan submit` command so a secondary command cannot weaken the invariant.
