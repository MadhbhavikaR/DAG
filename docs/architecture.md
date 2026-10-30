# Edit Architecture

Edit is organized as a layered, object-oriented application.

- `cli.py` owns command-line orchestration and delegates work to application services.
- `editor.py` coordinates file operations and mutation workflows.
- `filesystem.py` owns filesystem access and atomic persistence.
- `hashing.py` owns anchor generation, validation, and resolution.
- `indexing.py` owns the rebuildable index cache.
- `mutations.py` contains interchangeable mutation command objects.
- `output.py` owns JSON and human-readable presentation.
- `errors.py` defines application errors and parser errors.
- `text_utils.py` owns newline and line-text policies.
- `config.py` owns application limits and conventions.

## Design constraints

Application workflows should depend on cohesive abstractions rather than reach into unrelated implementation details. Each class should have one reason to change. Mutation behavior is represented by command objects; output and filesystem responsibilities remain separate from editing policy. Constructors are the composition boundary for dependencies, enabling isolated unit tests.

## Invariants

Never guess anchors; reject ambiguous hashes; verify source bytes before committing a mutation; validate cached indexes against source bytes; preserve newline conventions and file modes; default to structured JSON output. The index is disposable cache data and must never be required for correctness.
