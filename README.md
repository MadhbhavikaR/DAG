# Manager Agent Orchestrator

Manager is a deterministic, filesystem-backed workflow supervisor for code-change execution.

It is JSON-first by default. Every automation should consume JSON envelopes, not rendered text.

## Contributor First Step

Before making any change, read [AGENTS.md](./AGENTS.md). It defines the binding development contract, verification gates, and AGENTS hierarchy rules for this repository.

## Who This Is For

- Agent and tool authors integrating with manager commands
- Engineers operating managed task workflows in CI or local development
- Maintainers validating state integrity and protocol conformance

## What Manager Owns

- Workflow state under .manager
- Task and step lifecycle transitions
- Validation and commit gates
- Evidence and recovery-oriented error contracts

Do not edit .manager directly.

## Read In This Order

1. This file for quick command surface and guardrails.
2. docs/JSON_CONTRACT.md for response and error schema authority.
3. docs/OPERATIONS.md for execution loop, retries, and recovery flow.
4. skill/manager/SKILL.md for strict model behavior constraints.

## Quick Start

```bash
uv sync
uv run manager --prompt
uv run manager next
uv run manager submit-schema
uv run manager submit < result.json
```

For low-context execution, prefer this cycle:

```bash
uv run manager next
uv run manager context --compact --max-chars 1200
uv run manager submit-schema
uv run manager submit < result.json
```

## Command Reference

- uv run manager next
	Returns the active execution envelope and authoritative next action.
- uv run manager context
	Resolves allowed context records from the active envelope.
- uv run manager submit-schema
	Returns only the currently accepted submit schema for the active phase.
- uv run manager submit-schema --schema-path
	Returns a direct path to the active RETURN_SCHEMA cache file.
- uv run manager submit
	Submits a phase result and advances state if accepted.
- uv run manager bootstrap
	Returns prompt, startup command cycle, and compact status in one packet.
- uv run manager status --compact
	Returns a machine-oriented one-line status envelope.
- uv run manager verify
	Runs read-only consistency and integrity checks.
- uv run manager examples
	Emits minimal valid submit payload examples by phase.
- uv run manager learn add, uv run manager learn list, and uv run manager learn from-log --create-tasks
	Records and retrieves recurring operator/model friction.

## Protocol Sources

- JSON contract: docs/JSON_CONTRACT.md
- Operations guide: docs/OPERATIONS.md
- Schema catalog: docs/schemas/*.schema.json

## Non-Negotiable Invariants

- next_command is authoritative for progression.
- return_schema is authoritative for submit payload shape.
- agent_id in manager next is authoritative for task identity and must be echoed in every task interaction payload.
- Only manager may mutate lifecycle state.
- Step IDs are monotonic and never reused after archival.
- A ready step is promoted to active only by manager next.
- Completion requires DONE_WHEN plus validation/commit gates.

## Evidence Requirements

- Capture concrete evidence for analysis, validation, and failures.
- When file paths are submitted and Git is available, evidence includes file path, filename, and blob hash for durable reference.
- Use manager submit-schema before every submit to avoid schema drift.
- Use manager context before actions that depend on prior records.

## Diagnostics

- Runtime error telemetry is appended to .manager/runtime/error-log.ndjson.
- Each record includes command, argv, submitted input, and rendered output.
- Active RETURN_SCHEMA cache is stored at .manager/runtime/return-schema.json.

## Task Identity and Filenames

- Task files use sortable fixed-width names, for example:
	TODO-00-ACTIVE-03-S00001T00001.md
- Decomposition task IDs remain hierarchical, for example:
	S00001T00001-0000001-0000001

## Test Suite

```bash
uv run --system-certs pytest -q
```

Runtime implementation uses only the Python standard library.

## Release

- Application version: 1.0.0-rc
- Agent skill entrypoint: skill/manager/SKILL.md
