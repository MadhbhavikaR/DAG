# ADR-011: Actionable errors

## Decision
Recoverable errors always contain stable actionable fields: `error`, `what`, and `do`.

The runtime error contract is JSON-first. Optional `hint` and `gotcha` fields may be included for high-frequency corrective guidance.

## Rationale
A weak worker should not have to infer its recovery operation.

Structured JSON errors reduce parsing ambiguity and enable deterministic wrapper recovery logic.
