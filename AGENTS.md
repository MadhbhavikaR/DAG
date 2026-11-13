# Agent Engineering Contract

This file is authoritative for all automated and human contributors. Read it before changing code, tests, workflows, configuration, or documentation.

## 1. Repository and branch

- Repository: `MadhbhavikaR/DAG`.
- The only working branch is `DAG-Nano-4gb-NVR-AI`.
- Never create or switch to another development branch.
- Never push project work to `main` or `DAG-Template-Python`.
- Keep the working branch buildable and internally consistent after every commit.
- Do not claim that hardware validation occurred unless it was actually performed on the target hardware.

## 2. Mandatory Ralph Loop

For every story or feature, repeat this loop until its acceptance criteria pass:

1. Research the relevant standards, platform constraints, APIs, libraries, threat model, and alternatives.
2. Create or update the root `todo.md` before implementation. Break the work into atomic checklist items with status, dependencies, verification commands, and acceptance criteria.
3. Analyze requirements and record material architectural decisions in ADRs and decision alternatives/trade-offs in DAR documents.
4. Implement the smallest complete vertical slice.
5. Add tests that mirror the source module structure.
6. Run formatting, linting, static checks, unit tests, integration tests, dependency/security checks, and build checks applicable to the change.
7. Review correctness, security, reliability, performance, memory, CPU, thermal and maintainability impacts.
8. Update documentation and `todo.md` to reflect verified status.
9. Commit and push to the single working branch.
10. Report completed work, evidence, limitations, risks, and the recommended next iteration.

Do not mark a task complete based only on code being written. Require passing verification evidence. If a test needs unavailable hardware, mark it as pending hardware validation.

## 3. Commit and version policy

Every commit message must begin with exactly one of:

- `chore:` maintenance, tooling, repository governance, or documentation-only changes.
- `feat:` a completed atomic feature.
- `fix:` a bug fix.
- `release:` release preparation/publication commit.

Every completed atomic feature increments the SemVer minor version by one and updates all authoritative version metadata in that same feature commit. For example, 0.1.0 -> 0.2.0. Bug fixes and chores do not increment the version unless they are part of a feature completion. Release commits must not introduce untested application behavior.

Do not combine unrelated features in one commit. A feature commit must include its implementation, tests, documentation, and version update. Never claim a push or commit succeeded until the GitHub operation confirms it.

## 4. Release policy

- Releases use semantic versioning.
- Every release is represented by a `release:` commit and a matching annotated Git tag.
- Pushing a valid release tag triggers GitHub Actions.
- Release workflow runs the release test suite exactly once for that release attempt, and publishes the GitHub Release only if validation succeeds.
- A failed release validation must not publish a release.
- Keep the release tag format and workflow validation documented and consistent.

## 5. Architecture and code quality

- Use a configurable, event-driven modular monolith. One deployable process; explicit internal module boundaries.
- Apply SOLID, DRY, KISS, YAGNI, separation of concerns, dependency inversion, and appropriate design patterns without overengineering.
- Keep domain logic independent from transport, storage, inference backends, and notification providers.
- Prefer explicit interfaces, typed domain models, bounded queues, backpressure, timeouts, cancellation, and deterministic shutdown.
- Avoid unbounded buffering, unnecessary threads/processes, heavyweight services, and mandatory cloud dependencies.
- Do not put credentials, tokens, private RTSP URLs, or personal data in source, logs, fixtures, or documentation.
- Treat NVR and camera input as untrusted network input. Bound parser memory and reject malformed or oversized messages safely.
- Never expose NVR HTTP/ISAPI or RTSP endpoints to the public Internet.
- Make security-sensitive features opt-in and document privacy, consent, retention, and access controls.

## 6. Jetson Nano constraints

- Target: Jetson Nano 4GB, JetPack 4.6.6, L4T 32.7.6, Ubuntu 18.04, ARM64.
- Preserve compatibility with the installed CUDA/TensorRT/GStreamer stack; do not assume modern JetPack APIs.
- Validate Rust compiler, libc, dependency MSRVs, linker, and native library compatibility on the actual target before declaring deployability.
- Keep CPU, RAM, GPU memory, decoder sessions, concurrent inference, and queue sizes configurable and bounded.
- Prefer event-triggered inference and NVR substreams. Do not continuously run expensive inference across all 13 feeds without measured evidence that the device can sustain it.
- Record benchmark conditions and measurements; never invent performance numbers.

## 7. Testing

- Test directory structure mirrors source module structure.
- Every parser, state machine, rule, configuration validator, and error path receives focused tests.
- Include malformed input, timeouts, reconnects, duplicates, backpressure, cancellation, and resource-bound tests where relevant.
- Use deterministic fixtures and mock servers for hardware-independent tests.
- Keep hardware-in-the-loop tests separate and explicitly marked.
- CI must run the relevant quality and test suite. Every release runs the release suite once before publishing.

## 8. Documentation

- `docs/QUICKSTART.md` is the canonical quick-start guide and must be kept usable.
- `docs/architecture/ADR/` stores Architecture Decision Records.
- `docs/architecture/DAR/` stores Decision Analysis and Review records.
- Keep architecture, configuration reference, installation, operations, security, testing, and release documentation synchronized with shipped behavior.
- Use Markdown and consistent templates. Link sources for researched technical claims.
- Never document a planned feature as implemented.

## 9. Configuration

- No environment-specific IP, credentials, thresholds, retention periods, zones, or model paths hard-coded in business logic.
- Provide validated configuration with documented defaults and safe examples.
- Keep secrets outside tracked configuration files. Support protected environment files or equivalent secret providers.
- Validate configuration before starting network listeners or inference.
- Explain precedence between defaults, config files, and environment overrides.

## 10. Completion reporting

For each iteration report: commit SHA and branch, files changed, version impact, tests actually run and their results, unverified hardware assumptions, security/NFR review, remaining TODOs, and the recommended next atomic feature.
