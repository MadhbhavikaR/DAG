# Edit Agent Skill

Use the hash-anchored protocol for single-file edits: search via stdin, read bounded context using an observed hash, make the smallest mutation, and retain returned new anchors. On stale or ambiguous hashes, repeat search/read; never guess. create/rewrite/replace/insert read content from stdin. Search is literal unless `--regex` is set. JSON is the default output; `--human` is for direct human interaction. Consult `docs/JSON_CONTRACT.md` and `docs/OPERATIONS.md`.
