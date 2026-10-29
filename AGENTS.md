# AGENTS Contract

## Purpose

Project-wide contract for change discipline, verification gates, and AGENTS hierarchy behavior.


## Progressive Disclosure Entrypoints

1. Start with [README.md](./README.md) for runtime scope, setup, and execution surface.
2. Use [docs/README.md](./docs/README.md) for architecture and API doc navigation.
3. Use [docs/specs/README.md](./docs/specs/README.md) for implementation plans, constraints, and execution checklists.
4. Walk down the AGENTS chain and obey the nearest child contract for the files you change.

## Non-Negotiable Global Rules

- AGENTS.md files are binding contracts for their subtree.
- Follow SOLID, DRY, KISS, and YAGNI principles. Treat security, performance, and other NFRs as first-class concerns. Reuse existing code before introducing new abstractions.
- Use object-oriented design where it improves clarity and maintainability.
- One class per Python file.
- Use `uv` with `--system-certs` for Python commands.
- A change is incomplete until both pass:
  - `uv run --system-certs ruff check src tests`
  - `uv run --system-certs pytest -q`
- Keep architecture/docs/spec contracts synchronized with runtime behavior in the same change.
- Every extension directory containing `extension.yaml` must include `resources/help/README.md`.
- New extension work must comply with [docs/architecture/extension-authoring-rules.md](./docs/architecture/extension-authoring-rules.md) when that path exists in the current repository.
- `lib/tools/` is an internal boundary; edit under it only when explicitly requested.
- Use the manager tool to create stories, tasks, steps, evidence, knowledge, workflows, and todo items. For this repository, run:
  - `uv --system-certs run --project lib/tools/manager manager --help`
  - `uv --system-certs run --project lib/tools/manager manager --prompt`
- Always create stories/tasks and follow the manager workflow strictly.
- No silent fallback behavior for correctness-critical paths; exceptions must be handled or logged with appropriate severity.
- CLI commands must not block waiting for stdin unless the command explicitly requires stdin input by contract.
- All user-facing command failures must use one deterministic five-field error contract: `error`, `what`, `do`, `hint`, `gotcha`.
- `error` must be stable UPPER_SNAKE_CASE; `what` describes failure only; `do` provides exact next action; `hint` is state-aware guidance; `gotcha` warns about common recovery mistakes.
- Error guidance must be command/state-valid and must not recommend unavailable transitions.

## Strict Anti-Deviation Workflow

1. Identify target files and all ancestor/child AGENTS contracts.
2. Read applicable contracts before editing.
3. Identify root cause and regression surface before patching.
4. Apply surgical changes that preserve existing contracts unless intentionally revised.
5. Update the nearest owning docs/specs/contracts whenever behavior or structure changes.
6. Run required verification gates.
7. Report what changed, what was validated, and any intentionally unchanged areas.

## Documentation And Specs Policy

- `README.md` stays concise: overview, setup, execution commands, and key links.
- Durable architecture and API references live under `docs/`.
- Agent-oriented implementation plans and execution specs live under `docs/specs/`.
- Specs should be structured for fast scanning: summary first, then constraints, then execution details.

## Hierarchy Model

- Parent AGENTS defines broad contract.
- Child AGENTS defines local implementation rules and tighter constraints.
- Nearest AGENTS wins for local details; parent rules still apply unless the parent explicitly delegates.
- Child contracts must never weaken parent safety or quality gates.

## Closeout Checklist

1. Re-check changed paths against the AGENTS chain.
2. Update impacted AGENTS/README/docs/spec links.
3. Remove stale or contradictory contract text.
4. Run required validation commands.
5. Summarize completed verification and remaining risk (if any).


## Child Docs Index

- [src/AGENTS.md](./src/AGENTS.md): Package layout and module conventions for runtime source code.
- [tests/AGENTS.md](./tests/AGENTS.md): Test design, fixtures, and assertion conventions.
- [docs/AGENTS.md](./docs/AGENTS.md): Documentation structure and contract-language conventions.