# ADR-021: Lock integrity updates and validate managed record schemas strictly

**Status:** Accepted

## Decision

The integrity manifest is manager-owned state and is written only while holding the exclusive workspace lock. Managed task and step records are validated against the complete canonical frontmatter schema at startup.

## Why

The specification requires every mutation to occur under the workspace lock and requires startup validation of managed state. Treating the integrity manifest as an exception creates an unlocked mutation path. Accepting partial task or step frontmatter permits malformed managed state to survive until a later phase.

## Consequences

- Integrity refresh is serialized with all other manager mutations.
- Task and step records with missing canonical frontmatter fields fail closed with actionable corruption diagnostics.
- Numeric and enumerated managed fields are validated before state reconstruction.
