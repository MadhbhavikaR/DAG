# ADR-048 — Domain Model Boundaries and Command Dispatch

- **Status:** Accepted
- **Date:** 2026-10-30

## Context

The CLI module combined argument parsing, command routing, and command execution. The core module also declared several unrelated domain classes alongside persistence behavior. These responsibilities made the package harder to test and change independently.

## Decision

- Keep one production class per Python module.
- Place task identity rules in `manager.domain`.
- Place `ManagerError`, `Task`, `Step`, and `Submission` in focused modules.
- Keep `Store` as the persistence facade in `manager.core` and delegate Git operations to `GitRepository` in `manager.git_repository`.
- Keep argument parser behavior in `manager.parser`.
- Encapsulate command selection and stdin requirements in `CommandDispatcher`.
- Preserve the established `manager.core` imports as a compatibility facade for existing callers.

Stateless validation and formatting operations remain functions. They do not gain artificial object state or wrapper classes.

## Consequences

- Domain models and parser errors can be tested independently.
- Command routing and stdin policy have explicit test seams.
- Existing imports from `manager.core` remain valid.
- The filesystem store remains a large responsibility and is a candidate for subsequent decomposition into persistence repositories and integrity services. This ADR does not claim that the entire application has completed that decomposition.


## State Integrity Follow-up

Ordinary initialization validates existing managed state and does not reconcile transient execution state or refresh the integrity manifest after a mismatch. A read path must not legitimize unexpected state changes. Explicit administrative repair remains a separate future capability and must preserve an auditable before/after record.
