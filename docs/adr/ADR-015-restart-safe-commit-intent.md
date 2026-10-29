# ADR-015: Persist manager commit intent before Git mutation

## Decision
Before a manager-created step or final commit, persist the canonical commit message and transition the managed record into its committing state. After a restart, inspect the current Git HEAD and recover the recorded commit when it matches the pending intent.

## Rationale
A process can terminate after Git has created a commit but before the managed Markdown projection records its hash. Retrying blindly would create duplicate commits or violate the intended one-commit gate.

## Consequence
Commit phases contain durable intent, and recovery is deterministic from managed state plus Git metadata.
