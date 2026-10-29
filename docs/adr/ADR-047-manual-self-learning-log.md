# ADR-047 — Manual Self-Learning Log for Manager Improvement

- **Status:** Accepted
- **Date:** 2026-10-04

## Context

Weak-model operation reveals repetitive protocol friction (schema mistakes, context misuse, recovery loops). This information is often lost across sessions, making targeted manager hardening slower.

## Decision

Add a manager-owned manual learning log with structured commands:

- `manager learn add` to append an issue record.
- `manager learn list` to query recent records.

Learning records include task/phase context, severity, issue statement, optional error code, impact, suggestion, and evidence snippets.

The learning log is manager-owned state under `.manager`, written only through manager commands.

## Consequences

- Recurrent operational friction is captured as durable, queryable evidence.
- Improvement backlog generation becomes explicit and auditable.
- No lifecycle authority is delegated to the model; learning is observational metadata only.
- Operational teams can prioritize hardening by severity and frequency.
