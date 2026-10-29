# ADR-027: Centralize manager-owned task transition authority

## Decision
All task lifecycle mutations use one manager-owned transition guard derived from the specification's task transition table. Idempotent transitions to the current state remain successful; illegal transitions are rejected before persistence.

## Why
A transition table that exists only as constants is not sufficient if individual commands can assign lifecycle state directly. Centralizing the guard makes the lifecycle rule executable at every mutation boundary and produces the required actionable diagnostic when a caller attempts an illegal transition.

## Consequence
Task lifecycle commands and execution paths must request a legal state transition through the manager guard. Phase-specific gates remain responsible for determining when a legal transition is semantically permitted, while the transition guard enforces the lifecycle graph itself.
