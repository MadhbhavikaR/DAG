# ADR-023: Enforce the final commit boundary

**Decision:** The manager's final integration commit may include only repository paths authorized by the task's implementation steps.

**Why:** Step commits establish the task's approved application boundary, but later uncommitted edits can otherwise be swept into the final commit. A final commit must not silently absorb unrelated work.

**Consequence:** The manager computes the union of all step `may_edit` paths and rejects any uncommitted path outside that set. Restart recovery applies the same check to the recovered commit.
