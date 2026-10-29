# Architecture

CLI dispatch lives in cli.py; edit.py delegates for compatibility. config.py owns limits; errors.py owns typed errors; text_utils.py handles text normalization; filesystem.py handles safe reads/writes; hashing.py creates/validates anchors; indexing.py validates the cache; mutations.py implements replace/insert/delete; editor.py orchestrates edits; output.py renders JSON/human output. Runtime dependencies are standard library only.

Invariants: never guess anchors, reject ambiguous hashes, verify bytes before mutation commit, validate cache against source bytes, and default to JSON.
