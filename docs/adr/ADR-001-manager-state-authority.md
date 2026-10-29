# ADR-001: Manager is the sole workflow-state authority

## Decision
All workflow records, identifiers, filenames, frontmatter, state transitions, and durable evidence under `.manager/` are created and mutated only by Manager.

## Rationale
This preserves deterministic transitions, prevents invented IDs and roles, and makes restart reconstruction possible from managed files alone.

## Consequences
Application source remains model-editable only inside the current execution boundary. `.manager/` is never a model write surface.
