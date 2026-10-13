# Test contract

Tests under `tests/` must remain deterministic and offline. Use `uv run python -m unittest discover -s tests -v`. Keep source-inspection tests focused on invariants where importing Calibre is unavailable. Update expectations whenever source layout or archive contents change.
