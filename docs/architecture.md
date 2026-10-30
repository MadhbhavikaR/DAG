# Edit Architecture

Edit is a layered, object-oriented command-line application.

## Application layer

- `cli.py` contains the composition root and delegates command execution to focused adapters.
- `StandardInput` isolates stdin access.
- `TargetParser` owns hash/range target parsing.
- `JsonRequestDispatcher` validates and dispatches JSON requests.
- `CommandDispatcher` translates parsed CLI arguments into application-service calls.
- `FileEditor` coordinates use cases and receives filesystem, hashing, indexing, mutation, text, and output dependencies through its constructor.

## Domain and infrastructure

- `mutations.py` models replace, insert, and delete as interchangeable command objects. `MutationRegistry` allows additional strategies to be registered without changing editor orchestration.
- `ports.py` defines structural service contracts used by the application layer.
- `filesystem.py` owns safe reads, exclusive creation, atomic persistence, and transaction cleanup.
- `hashing.py` owns anchor generation, validation, and resolution.
- `indexing.py` owns the rebuildable index cache.
- `output.py` owns JSON and human-readable presentation.
- `errors.py` defines application and parser errors.
- `text_utils.py` owns newline and line-text policies.
- `config.py` owns application limits and conventions.

## SOLID decisions

- **Single Responsibility:** command parsing, stdin reading, request dispatch, file editing, persistence, mutation strategies, and output formatting have separate owners.
- **Open/Closed:** new mutation commands can be registered through `MutationRegistry`.
- **Liskov Substitution:** mutation implementations satisfy the same `MutationCommand` contract and can be substituted by the editor.
- **Interface Segregation:** `ports.py` exposes narrow contracts for the services used by the editor.
- **Dependency Inversion:** `FileEditor` accepts service contracts rather than constructing concrete infrastructure internally; defaults are composed at the application boundary.

## Invariants

Never guess anchors; reject ambiguous hashes; verify source bytes before committing a mutation; validate cached indexes against source bytes; preserve newline conventions and file modes; default to structured JSON output. The index is disposable cache data and must never be required for correctness.
