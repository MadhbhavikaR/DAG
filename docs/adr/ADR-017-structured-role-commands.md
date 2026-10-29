# ADR-017: Expose structured role-specific mutation commands

## Decision

Expose `manager plan submit` and `manager evidence add` as structured commands while retaining `manager submit` as the primary simple-model execution interface.

## Why

The specification permits role-specific authoring commands but requires them to remain structured. Explicit commands make administrative and role-specific mutations discoverable without moving orchestration decisions into the model.

## Consequence

The command parser must reject unsupported fields and every role-specific mutation remains manager-owned, locked, validated, and canonically rendered.
