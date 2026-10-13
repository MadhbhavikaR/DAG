# Build tooling contract

`build_plugin.py` builds an installable plugin ZIP from `src/`, keeping each runtime file at the ZIP root. Only required Calibre runtime files belong in the archive. Keep the builder standard-library-only, validate ZIP integrity and exact entries, and never commit generated ZIPs.
