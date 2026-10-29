# ADR-009: Manager-created Git commits

## Decision
When commit mode is enabled, Manager stages only permitted application files and creates the commit itself.

## Rationale
A model-supplied hash is only a claim; Manager-created commits can be verified against gates and boundaries.
