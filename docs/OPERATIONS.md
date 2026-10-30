# Operations Guide

This runbook describes the standard execution loop, rejection behavior, and operational guardrails.

## Standard Execution Loop

1. Run manager next.
2. If next_command is manager context, load only IDs listed in LOAD.
3. Execute only ACTION and stay within BOUNDARY.
4. Run manager submit-schema.
5. Submit one payload matching return_schema exactly.
6. Repeat until manager returns NO_TASK.

## Schema-Safe Submit Pattern

- Always refresh schema immediately before submit.
- Use manager submit-schema --schema-path when a direct file path is easier for tools.
- Keep textual payload fields under output_limit.

## Failure Recovery Loop

When a command returns an error envelope:

1. Read error, what, and do.
2. Execute do exactly.
3. If available, use hint and gotcha to avoid repeat mistakes.
4. For INVALID_SCHEMA, read schema_path or return_schema_path and resubmit.
5. When current external information is required, use research tools (for example web search) and cite evidence.

Do not improvise state edits or phase transitions outside manager commands.

## State Integrity and Rejection

- Startup and ordinary read commands validate existing authoritative state. They do not reconcile lifecycle state or refresh the integrity manifest to accept unexpected changes.
- A state-integrity mismatch is rejected. Preserve affected records and investigate before an explicit, reviewed administrative repair.
- A rejected operation must not change authoritative task, step, workspace, evidence, knowledge, or submission records. Diagnostic telemetry is separate.
- Rejection is scoped to that request. Do not block unrelated valid workflows unless authoritative workspace state itself cannot be trusted.
- Agents submit proposals through the command protocol. They must not write `.manager/` directly.

## Story and Step Control Rules

- manager next owns story and task activation order.
- Only manager transitions step/task state.
- Validation failures must be submitted as failures before retry.
- Blocked states must be resolved through block/unblock workflow.

## Operational Commands

- manager bootstrap
  Returns startup packet for low-context automation.
- manager status --compact
  Returns minimal machine-readable current state.
- manager verify
  Performs read-only integrity and consistency checks.
- manager examples
  Shows minimal valid submit payloads by phase.

## Learning Log Workflow

Capture recurring friction:

```bash
cat <<'JSON' | uv run manager learn add
{
  "issue": "Model adds unsupported fields during validation",
  "error_code": "INVALID_SCHEMA",
  "phase": "step_validation",
  "severity": "high",
  "impact": "retry loops",
  "suggestion": "echo allowed fields in error",
  "evidence": ["attempted extra key: foo"]
}
JSON
```

Review recent records:

```bash
uv run manager learn list --limit 20
```

Use this data to improve prompts, schemas, and runbooks.

## Evidence Checklist

- Include exact command and phase context.
- Include concrete failing outputs, not paraphrases.
- Include attempted corrective action and outcome.
- Prefer short, high-signal arrays over long narrative blocks.
- For file references, include repository path and Git blob hash when available.

## Diagnostics and Telemetry

- Agent-scoped error telemetry logs: .manager/runtime/error-<agent-id>-log.ndjson
- Agent-scoped command ring buffer (last ten commands): .manager/runtime/last-10-<agent-id>-log.ndjson
- Active schema cache: .manager/runtime/return-schema.json

Manager appends every command to the agent ring buffer.  
On an error, manager writes the buffered last ten records (including the failing command) to the agent error log, then clears the buffer.

These files are manager-owned diagnostics artifacts and should be inspected, not manually edited.

## Production Readiness Checklist

- Run manager verify before attaching an agent after restart.
- Validate responses against docs/schemas/*.schema.json.
- Reject unexpected payload shapes.
- Never mutate .manager outside manager commands.
