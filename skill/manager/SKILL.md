---
name: manager
description: Use the Manager Agent Orchestrator as the sole controller for repository task execution. Use when an agent must get the next execution envelope, load only permitted context, submit structured results, recover from protocol errors, and complete work without editing .manager directly.
---

# Manager Agent Orchestrator
Current release: 0.21.1

Use the `manager` CLI as the authoritative protocol surface. Treat `.manager/` as manager-owned state and never edit it directly.

## Low-context startup

```bash
uv run manager --prompt
uv run manager bootstrap
uv run manager next
```

Use `bootstrap` when context is limited. It returns startup commands, micro-cycle rules, and compact status.

## Standard execution loop

1. Run:

   ```bash
   uv run manager next
   ```

2. Read the envelope and obey:
   - `phase`, `role`, `objective`, `action`
   - `boundary`, `accept`, `load`
   - `return_schema`, `submit_command`, `next_command`
3. If `next_command` is `manager context`, load only listed IDs:

   ```bash
   uv run manager context --compact --max-chars 1200
   ```

4. Before submit, request active schema:

   ```bash
   uv run manager submit-schema
   ```

5. Submit one JSON object matching `return_schema` exactly:

   ```bash
   uv run manager submit < result.json
   ```

6. On errors, execute `do` exactly. Do not guess hidden state.
7. Repeat until `NO_TASK`.

## Non-negotiable rules

- Never write, rename, or delete files under `.manager/` directly.
- Never invent IDs, states, roles, evidence, or commit hashes.
- Never submit unsupported fields.
- Never bypass `next_command`.
- Never commit manually when manager governs commit transitions.
- Never claim completion without satisfying validation and commit gates.

## Useful commands

```bash
uv run manager status --compact
uv run manager verify
uv run manager examples
uv run manager learn add < issue.json
uv run manager learn list --limit 20
```
