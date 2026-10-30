# State Integrity Implementation TODO

**Source of truth:** This file tracks the state-integrity implementation. Do not use the Manager CLI or .manager task records to manage this plan.

**Policy:** Rejected operations must not mutate authoritative state. A rejected request must not block unrelated valid workflows. Manager alone owns authoritative state mutations; agent input is a proposal, never permission to write managed state directly.

## Baseline
- [x] Confirm branch and baseline architecture: Manager, commit d0cf925c92059c8b5317ddce6ae26915114e64b8.
- [x] Review root, src/, tests/, and docs/ AGENTS contracts.
- [x] Identify core mutation surfaces in Store: initialization/reconciliation, task and step persistence, support records, submissions, integrity manifest, and workspace metadata.
- [x] Identify CLI mutation entrypoints and the agent-facing next / context / submit protocol.
- [ ] Complete recursive inventory of all repository paths, extensions, scripts, and direct managed-state access. GitHub file access did not expose a recursive tree listing; complete this when a local checkout is available.

## Work plan
### 1. Eliminate mutation during reads
- [x] Stop load_tasks from rewriting task files when UUID text can be normalized in memory.
- [ ] Audit every load/read/verify/context/status path for writes, including normalization, index rebuilds, schema caches, and initialization.
- [x] Add a regression test proving task loading does not rewrite a record when UUID text is normalized in memory. (Execution pending: no local checkout/test runner is available in this session.)

### 2. Establish a single mutation boundary
- [ ] Inventory every write call and classify it as initialization, domain mutation, derived cache, telemetry, or repair.
- [ ] Route agent-originated changes through explicit application operations.
- [ ] Ensure no agent-facing operation can write authoritative .manager records directly.
- [ ] Make repair an explicit administrative operation; remove implicit correctness-critical repair from ordinary reads/startup.

### 3. Enforce operation authorization
- [ ] Validate agent identity against the active task and assigned scope for every mutation.
- [ ] Enforce phase, role/capability, task ownership, and step ownership centrally rather than relying on prompt instructions.
- [ ] Reject immutable identity and scope changes.
- [ ] Add stale-state/version preconditions to mutation requests.

### 4. Preserve domain invariants
- [ ] Centralize task and step transition validation.
- [ ] Validate task/step/evidence/reference consistency before persistence.
- [ ] Validate the complete proposed state before writing any record.
- [ ] Ensure rejected operations leave authoritative state byte-for-byte unchanged.

### 5. Make multi-record operations atomic
- [ ] Identify all operations that update multiple managed files.
- [ ] Implement transactional commit/rollback semantics for each operation.
- [ ] Prevent concurrent lost updates with lock + version/precondition checks.
- [ ] Keep integrity-manifest updates inside the same commit boundary.

### 6. Isolate agent execution
- [ ] Separate project edit permissions from Manager-owned state.
- [ ] Prevent path traversal, symlink, and direct .manager write paths at the execution boundary.
- [ ] Define explicit per-role writable project paths and read-only Manager context.
- [ ] Verify isolation with adversarial filesystem tests.

### 7. Adversarial verification
- [ ] Add rejection-without-mutation tests for malformed payloads, wrong agent, wrong phase, stale version, illegal transition, immutable-field changes, and out-of-scope paths.
- [ ] Add idempotency and concurrency tests.
- [ ] Add state-machine/property-based transition tests where practical.
- [ ] Verify one rejected operation does not prevent an independent valid operation.

### 8. Documentation and closeout
- [ ] Update JSON contract, operations guide, architecture decision records, and agent skill to match enforced behavior.
- [ ] Run uv run --system-certs ruff check src tests.
- [ ] Run uv run --system-certs pytest -q.
- [ ] Report remaining risks and unimplemented boundaries explicitly.

## Implementation notes
- Current persistence is filesystem-backed. Individual writes use atomic replacement, but a multi-file workflow is not thereby atomic.
- Store remains a broad facade; do not undertake a wholesale rewrite before mutation paths and invariants are covered by tests.
- The initial implementation change removes an implicit write from task loading. This is a narrow prevention fix, not proof that all read paths are now side-effect-free.