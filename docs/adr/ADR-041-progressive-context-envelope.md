# ADR-041 — Progressive Context Is Part of the Execution Envelope

## Status
Accepted

## Context
The manager specification requires `manager next` to expose only the context required by the current execution phase, and `manager context` to resolve only references reachable from that envelope. Planning requires accepted findings and decisions, while final validation may need prior manager-recorded evidence.

## Decision
The manager computes phase-specific `LOAD` identifiers from authoritative managed records:

- implementation: the current step's declared `load` IDs;
- planning: all current-task findings plus decisions whose latest lifecycle status is `accepted`;
- final validation: current-task evidence IDs;
- other phases: no implicit context.

`manager context` resolves only those IDs for the current envelope. Decision resolution records are considered when determining the latest decision status; proposed, rejected, or superseded decisions are not exposed as planning context.

`manager context` responses include explicit task and phase identity so weak workers can detect cross-task or stale-envelope usage without relying on conversational memory.

## Consequences
- Planning no longer requires the model to infer or rediscover accepted context from prior conversation state.
- Context remains bounded to stable manager-owned IDs rather than uncontrolled document dumps.
- A stale or unreachable context request fails closed with an actionable diagnostic.
- The manager remains the sole authority over which context is exposed to the model.
- Context consumers can verify envelope alignment (`task`, `phase`) before using resolved records.
