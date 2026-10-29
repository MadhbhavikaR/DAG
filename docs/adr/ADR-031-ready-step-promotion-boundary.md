# ADR-031: Ready Step Promotion Is Owned by `manager next`

## STATUS
Accepted

## CONTEXT
The execution-unit lifecycle defines `queued -> ready -> active` and treats `manager next` as the command that selects and exposes exactly one current unit of work. A model submission must therefore never be able to promote a `ready` step merely by submitting implementation output.

## DECISION
Only the manager's `next` envelope construction may perform the `ready -> active` promotion for the current implementation step. `manager submit` accepts implementation evidence only when the current step is already `active`.

## CONSEQUENCES
- A failed validation can return a step to `ready` without silently reactivating it.
- The next model turn must call `manager next` before implementation resumes.
- The implementation submission boundary cannot bypass the selection gate.
- Restarting the process preserves the `ready` state until the next manager selection.

## EVIDENCE
- Specification section 10.3: `queued -> ready -> active`.
- Specification section 12: `manager next` returns exactly one execution envelope.
