# ADR-033: Never Reuse Step Identifiers

## Decision
Implementation step identifiers are monotonically allocated per task across both the active `.manager/steps/` tree and archived superseded plans under `.manager/archive/`.

A new plan may restart its positional `sequence` at `1`, but it must receive fresh `STEP-####` identifiers. Archived step records therefore remain part of identifier history even after a plan is replaced.

## Why
The specification defines record identifiers as unique within a task and states that identifiers are never reused. Replanning and final-validation correction can supersede an existing implementation plan; deleting or archiving the old projection must not make its identifiers available for reuse.

## Consequence
- `sequence` describes ordering within the current plan.
- `STEP-####` identifies the durable execution record.
- Restarting a plan preserves identifier uniqueness while retaining the simple ordered sequence model.
- Recovery can distinguish a new corrective execution unit from its historical predecessor.
