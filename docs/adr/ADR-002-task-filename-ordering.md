# ADR-002: Fixed-width task identifiers and filenames

## Decision
Task IDs use fixed-width story/task/decomposition components and task filenames use a queue/state prefix followed by fixed-width priority and the task ID.

Example: `TODO-00-ACTIVE-03-S00001T00001.md`.

## Rationale
Lexicographic directory sorting then provides a deterministic human-visible queue ordering while the ID remains the authoritative identity.

## Consequences
The manager must generate filenames. Models must never invent or rename them.
