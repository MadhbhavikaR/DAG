# Edit Architecture

Edit is a layered, object-oriented command-line application.

- `cli.py` owns command-line parsing and dispatch.
- `editor.py` coordinates file operations and mutation workflows.
- `filesystem.py` owns safe reads and atomic persistence.
- `hashing.py` owns anchor generation, validation, and resolution.
- `indexing.py` owns the rebuildable index cache.
- `mutations.py` contains replace, insert, and delete command objects.
- `output.py` owns JSON and human-readable presentation.
- `errors.py` defines application and parser errors.
- `text_utils.py` owns newline and line-text policies.
- `config.py` owns application limits and conventions.

## SOLID design requirements

The intended design is based on single responsibility, open/closed mutation commands, substitutable service contracts, interface segregation, and dependency inversion. Application orchestration should depend on small abstractions, with concrete filesystem, hashing, indexing, and output implementations supplied at the composition boundary.

The current package/module split is an initial structural separation, not a claim of complete SOLID conformance. In particular, the CLI still contains orchestration and input-validation responsibilities together, and several helper classes expose static utility APIs rather than injected service contracts. These are explicit refactoring targets; they must be addressed with focused tests rather than hidden behind naming or documentation.

## Invariants

Never guess anchors; reject ambiguous hashes; verify source bytes before committing a mutation; validate cached indexes against source bytes; preserve newline conventions and file modes; default to structured JSON output. The index is disposable cache data and must never be required for correctness.
