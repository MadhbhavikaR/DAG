# ADR-044: Requirement Audit and Changed-File Diff Fidelity

## Status

Accepted

## Context

The specification requires an implementation result to report changed application files and requires the manager to verify those files against the repository diff when Git is available.

The previous implementation checked that reported paths were permitted and that unexpected current changes were reported, but it did not reject a reported path that had subsequently returned to its pre-step state.

## Decision

When Git is available, every path submitted in `changed_files` must be present in the current worktree delta relative to the task's recorded baseline. Git-tracked deletions remain valid because their paths appear in Git status even when the filesystem object no longer exists.

A submitted path that is not present in the current diff is rejected with an actionable `CHANGED_FILE_NOT_IN_DIFF` error.

## Consequences

- Implementation evidence corresponds to an actual repository change.
- Reverted/no-op files cannot be falsely reported as changed.
- Tracked deletions remain supported.
- The model receives a precise corrective instruction instead of a silent acceptance of inaccurate evidence.
