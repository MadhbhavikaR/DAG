# ADR-008: Append-only evidence

## Decision
Findings, decisions, validations, and commits are durable records; corrections create new records rather than rewriting history.

## Rationale
Provenance must survive failures and superseded reasoning.
