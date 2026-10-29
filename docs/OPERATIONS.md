# Operations Guide

1. Search a distinctive literal query through stdin.
2. Read around a returned hash if more context is needed.
3. Send exact content to replace/insert through stdin.
4. Inspect the JSON result and use its new hashes.
5. If stale/ambiguous, search/read again; never guess.

Ranges use START_HASH..END_HASH, inclusive and in file order. Insert accepts one anchor only. Mutations atomically replace the file, check for concurrent changes, preserve mode where possible, and maintain newline convention. The index cache lives in the OS temp directory.

Recovery: STALE_HASH/STALE_FILE means refresh anchors; AMBIGUOUS_HASH means choose a unique fresh anchor; HASH_COLLISION means change content; MISSING_INPUT/MISSING_QUERY means provide stdin; INVALID_RANGE means check endpoint order.
