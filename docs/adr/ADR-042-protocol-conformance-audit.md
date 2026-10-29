# ADR-042: Protocol Conformance Audit

**Status:** Accepted

## Decision

The implementation treats the specification's required protocol scenarios as an explicit conformance surface. The test suite must exercise the complete model-facing lifecycle, including role assignment, selection boundaries, validation/commit gates, restart recovery, idempotency, managed-record corruption, and terminal `NO_TASK` behavior.

## Rationale

The manager is a protocol controller, not merely a collection of persistence helpers. Passing isolated unit tests is insufficient if the complete weak-model loop can still violate an invariant at a phase boundary.

## Consequence

Future changes must preserve the protocol-level regression suite. New lifecycle or envelope behavior must add a scenario-level regression test before it is considered conforming.
