# ADR-005: Progressive context loading

## Decision
Execution envelopes reference stable knowledge IDs; `manager context` resolves only reachable records.

## Rationale
Most actions need only a small subset of accumulated reasoning.
