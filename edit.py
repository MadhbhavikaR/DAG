#!/usr/bin/env python3
"""Compatibility entry point for running Edit from a source checkout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from edit.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
