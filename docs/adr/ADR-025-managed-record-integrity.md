# ADR-025: Validate Managed Record Semantics, Not Only Syntax

## Decision
Manager startup validation checks timestamp format, task identifier/sequence agreement, and required task-definition content for actionable states.

## Why
The specification makes lifecycle metadata authoritative. Syntactically valid Markdown can still encode contradictory or non-canonical state. These checks make tampering and partial corruption fail closed before mutation.

## Consequence
Managed records must retain canonical ISO-8601 timestamps with explicit offsets, task sequences must agree with their IDs, and planned/active/expanded tasks must retain `WHAT` and `DONE_WHEN`.
