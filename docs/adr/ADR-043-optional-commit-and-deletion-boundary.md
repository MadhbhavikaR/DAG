# ADR-043: Optional Step Commits and Deletion-Aware Boundaries

**Status:** Accepted

## Decision

Honor the specification's distinction between `required`, `optional`, and `disabled` step commit policies. An optional step may complete after validation without a manager-created commit when the model explicitly submits `skip_commit`; required commits cannot be skipped. Git-tracked deletions are valid application changes and remain subject to the same `may_edit` boundary.

## Why

The implementation previously treated every Git-enabled step as requiring a commit and rejected deleted paths merely because the filesystem path no longer existed. Both behaviors narrowed the specified contract.

## Consequences

The execution envelope exposes the legal optional-commit outcome, the manager records skipped optional commits as evidence, and boundary verification recognizes Git-tracked deletions without weakening path or managed-tree protections.
