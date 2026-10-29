# Schema Catalog

This directory defines the authoritative JSON response contracts for manager.

## What Is Covered

- Runtime command envelopes
- Learn RCA envelope: learn-from-log.schema.json
- Runtime error envelopes

## How To Use

- Validate each manager response against the matching schema before acting.
- Treat schema validation failures as protocol failures.
- For submit flows, prefer active runtime schema from return_schema or return_schema_path.

## Design Intent

- Schemas are intentionally strict.
- Most envelopes use additionalProperties: false.
- Optional fields are declared explicitly.

- task-add-input schema supports items[] for multi-request decomposition into individual stories/tasks.
## Maintenance Rule

When a response shape changes:

1. Update the relevant schema file.
2. Update contract tests in tests/test_manager.py.
3. Verify runtime output matches the revised schema.

## Contract Test Coverage

Iteration33JsonContractSchemaTests validates live manager output against this catalog.
