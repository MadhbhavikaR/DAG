# ADR-035: Persisted workspace commit policy is authoritative

## Decision

The workspace's `commit_mode` stored in `.manager/workspace.md` is authoritative after workspace initialization. Git discovery is used only to choose the initial policy when the workspace has no persisted policy yet.

## Why

The orchestration specification treats commit mode as workspace policy. A transient change in Git availability must not silently change the commit requirements of newly created tasks or alter the meaning of an existing workspace.

## Consequences

- A non-Git workspace remains `disabled` even if Git later becomes available.
- A Git-enabled workspace remains `enabled` even if Git later becomes unavailable; required commit operations will then fail with the appropriate Git/recovery diagnostic rather than silently changing policy.
- `workspace.md` remains the durable source for this policy.
