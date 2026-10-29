# ADR-018: Preserve decision lifecycle during supersession

## Decision
A new decision that declares `SUPERSEDES` an accepted decision remains `proposed` until independently resolved. The earlier decision remains `accepted` until the replacement is accepted; only then does the manager append an immutable `superseded` resolution referencing the replacement.

## Why
The specification defines the decision lifecycle as `proposed -> accepted | rejected` and `accepted -> superseded`. Marking the old decision superseded when the replacement is merely proposed would create an invalid lifecycle and could leave the workspace without an effective accepted choice if the replacement is later rejected.

## Consequence
Supersession is a two-record transition: proposal records the relationship, while acceptance records the supersession event. Rejected replacements do not alter the accepted decision.
