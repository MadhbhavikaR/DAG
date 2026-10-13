# Download modules

## Purpose
Define contracts for service-specific download implementations.

## Ownership
- `lgli_download.sh` handles downloads through the configured Library Genesis mirror.
- `zlib_download.sh` handles downloads through the configured Z-Library mirror and local cookie jar.

## Local Contracts
- Functions expect `TMP_DIR`, `ZLIB_URL`, `ZLIB_COOKIES_FILE`, and helper functions such as `get_json_value` and `sanitize_filename`.
- Selection indices correspond to objects in the temporary search results.
- Cookies are local runtime data and must never be committed.

## Work Guidance
Validate required fields and fail safely when a source is unavailable.

## Verification
Run shell syntax checks and test with non-sensitive fixtures where possible.

## Child DOX Index
No child DOX files currently.
