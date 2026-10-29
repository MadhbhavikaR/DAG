# JSON Contract

Manager is JSON-first. Automations must consume JSON envelopes as the protocol surface.

Text output is for human compatibility only.

## Command to Schema Mapping

- manager next -> docs/schemas/next.schema.json
- manager context -> docs/schemas/context.schema.json
- manager status -> docs/schemas/status.schema.json
- manager status --compact -> docs/schemas/status-compact.schema.json
- manager submit-schema -> docs/schemas/submit-schema.schema.json
- manager bootstrap -> docs/schemas/bootstrap.schema.json
- manager verify -> docs/schemas/verify.schema.json
- manager examples -> docs/schemas/examples.schema.json
- manager learn add -> docs/schemas/learn-add.schema.json
- manager learn list -> docs/schemas/learn-list.schema.json
- manager learn from-log -> docs/schemas/learn-from-log.schema.json
- error responses -> docs/schemas/error.schema.json

## Envelope Guarantees

- Command responses are stable, schema-validated objects.
- Unknown fields are rejected unless declared optional in the schema.
- Consumers should validate each envelope before acting on it.
- Active task envelopes include agent_id as a UUIDv4 string. Consumers must reuse that value for every task interaction payload.

When manager next has no actionable work, it returns a structured NO_TASK envelope with recovery guidance, suggested commands, and schema_path for task creation.

Task intake supports one-object payloads and batch payloads via items[] to decompose multi-request input into individual stories/tasks before implementation.

## Execution-Critical Fields

- next_command
	Authoritative next protocol action. Do not infer alternatives.
- return_schema
	Authoritative payload contract for manager submit in the active phase.
- agent_id
	Authoritative task interaction identity from manager next. It is a UUIDv4. Echo it in every submit, finding, decision, evidence, and plan-submit payload.
- output_limit
	Authoritative per-field text budget for submitted textual values.
- return_schema_path
	Direct path to a cached file containing the active return_schema object.
- schema_path (NO_TASK and selected error cases)
	Direct path to an input schema file that should be used for the recovery command.

## Error Envelope

All protocol errors include:

- error: stable error code
- what: precise failure reason
- do: exact command sequence to execute for recovery

Optional helper fields:

- hint: additional state-aware reference (schema location, current phase guidance, and follow-up context)
- gotcha: explicit anti-patterns to avoid while recovering
- schema_path: direct path to the active RETURN_SCHEMA file, when relevant

## Consumer Rules

- Parse JSON only.
- Treat non-zero exit and error envelope as authoritative failure.
- Execute do exactly before retrying.
- For INVALID_SCHEMA, prefer schema_path or return_schema_path over local guesses.

## Compatibility Note

Rendered text remains useful for local debugging and legacy tests, but it is not the normative integration surface.
