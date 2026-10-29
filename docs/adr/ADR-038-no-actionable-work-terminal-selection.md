# ADR-038: No-Actionable-Work Terminal Selection

**Status:** Accepted

## Decision

`manager next` returns `NO_TASK` only after evaluating persisted task ordering, active execution state, expanded-parent coordination, and actionable child tasks. Stale ordering metadata must not resurrect completed work after restart.

## Why

Terminal selection is part of the durable orchestration contract, not merely a convenience of the interactive CLI.

## Consequences

Restart reconstruction and terminal selection use the same manager-owned state invariants, and the `NO_TASK` condition remains deterministic and auditable.
