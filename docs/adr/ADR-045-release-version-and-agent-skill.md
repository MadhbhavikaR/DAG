# ADR-045 — Release Version and Agent Skill

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

The Manager release needs an explicit release identifier distinct from the persisted managed-storage format. Agents also need a standard skill artifact describing the manager-mediated execution protocol.

## Decision

The application release is `1.0.0-rc` (normalized to `1.0.0rc0` by PEP 440 tooling). The managed storage format remains `1.0.0` and is not changed by this release because no storage-format migration is introduced.

The repository provides the agent skill at `skill/manager/SKILL.md`. The skill directs agents to use the manager CLI, respect execution envelopes, avoid direct `.manager` edits, and use the manager's `ERROR / WHAT / DO` recovery contract.

## Consequences

- Package metadata and runtime `__version__` identify the release as `1.0.0-rc`.
- Existing `.manager/VERSION` records remain compatible with the `1.0.0` storage format.
- Agents can discover a standard skill artifact from the repository without learning internal implementation details.
