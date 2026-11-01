# ADR-050 — Portable API-Only Workflow Library

- **Status:** Accepted
- **Date:** 2026-11-01

## Context

The Manager distribution is intended to be installed and used as a Python wheel across different agent hosts. It must not depend on one execution mechanism, such as Docker, subprocesses, an IDE agent, or an MCP server. The host executes the model/agent; Manager provides the workflow and API surface.

A Python library cannot enforce an OS security boundary against arbitrary code running with the same user privileges and filesystem access. Treating a payload field such as `agent_id` as proof of identity would also permit a caller to impersonate another assigned agent.

## Decision

- The wheel provides APIs, domain workflow, policy enforcement, validation, and persistence.
- The wheel does not launch, supervise, schedule, or terminate LLM agents.
- The wheel does not claim to sandbox processes or prevent direct filesystem access by a hostile process.
- CLI, IDE, MCP, container, and other integrations are host adapters over the same public API. They must not implement separate workflow rules.
- An integration must establish the caller's principal outside untrusted agent payload data and pass a trusted principal/capability context to Manager.
- Payload `agent_id` is an assignment/correlation value. It is never sufficient authentication by itself.
- Manager authorizes each operation against the trusted principal, task assignment, current phase, role, step ownership, and explicit resource scope.
- Agent-originated changes are proposals. Manager validates and commits authoritative state.
- The host remains responsible for OS-level process isolation and filesystem permissions. The documented safe deployment mounts or exposes `.manager/` only to the Manager service, not to agent code.
- Storage implementations remain behind the API so filesystem and future transactional backends can be used without changing agent-facing workflow contracts.

## Consequences

- The core package remains portable and does not acquire Docker, MCP, IDE, or model-provider dependencies.
- Multiple hosts can share one workflow contract and one policy implementation.
- Security guarantees are split explicitly: Manager enforces application authorization and state invariants; the host enforces OS-level isolation.
- A same-process integration that exposes unrestricted Python object access is not a security boundary. Strong isolation requires a separate service/process or OS controls owned by the host.
- Public API design must avoid exposing raw `Store` mutation methods to untrusted agent callers.
