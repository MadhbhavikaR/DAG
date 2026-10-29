# ADR-026: Enforce phase guards on active-task decomposition

## Decision
An active task may enter `expand` only from the `analysis` or `planning` execution phases. A planned task may enter `expand` directly.

## Why
The task lifecycle permits `active -> expand`, while the execution lifecycle defines decomposition as a consequence of analysis or planning. Allowing an active implementation, validation, or commit phase to jump directly to decomposition would bypass the bounded execution unit and its validation gates.

## Consequence
The CLI rejects active-task expansion from implementation, step validation, step commit, final validation, or final commit with an actionable transition error. Existing planned-to-expand and analysis/planning-to-expand flows remain valid.
