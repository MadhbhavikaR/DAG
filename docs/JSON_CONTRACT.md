# JSON Contract

Success JSON is written to stdout; errors are written to stderr with a non-zero exit. --human is not the automation protocol.

All successes include ok: true and operation. create/rewrite return lines; read returns context records; search returns count, truncated, and matches; mutations return lines_changed, lines_after, and new anchors/context where possible. Fields vary by operation.

Errors include ok: false, error, and message; action is included when recovery guidance exists. Hashes must come from the latest read/search response for the same file version.

Content and search queries come from stdin. Search is literal unless --regex is passed. Range endpoints are inclusive and written START_HASH..END_HASH. --json-input accepts one request object from stdin. JSON is compact UTF-8 output.
