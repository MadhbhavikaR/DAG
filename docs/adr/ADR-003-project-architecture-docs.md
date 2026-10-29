# ADR-003: Project architecture decisions live under docs/adr

## Decision
Every Manager workspace may contain project-level architectural decisions under `docs/adr/`. Manager-owned operational state remains under `.manager/`.

## Rationale
Architectural rationale belongs to the project and should remain readable and version-controlled independently from transient orchestration state.

## Consequences
Manager does not treat `docs/adr/` as workflow state. Models may read project ADRs when a manager execution envelope permits them as repository context.
