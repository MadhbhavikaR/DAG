# ADR-032: Reject symbolic links inside the managed tree

## Status
Accepted

## Context

The manager owns every path below `.manager/`, and managed records are the
filesystem-backed source of durable orchestration state. A symbolic link inside
that tree can redirect a manager read or write outside the workspace or make a
path appear to be manager-owned while its bytes are controlled elsewhere.

## Decision

The manager rejects `.manager` itself, managed subdirectories, managed files,
and `.manager/.manager.lock` when any of them are symbolic links. The check is
performed before managed-state mutation and during startup validation.

## Rationale

The ownership boundary must be structural, not dependent on the target of a
filesystem link. Failing closed prevents redirected reads, writes, and locks
from crossing the manager's ownership boundary.

## Consequences

- A workspace containing a managed-tree symlink requires administrative repair
  before normal manager commands continue.
- The manager remains compatible with ordinary regular files and directories.
- Application-repository symlinks outside `.manager` remain subject to the
  existing repository path-boundary rules rather than this managed-tree rule.

## Verification

Regression tests cover symlinked managed files, managed directories, and the
manager lock path.
