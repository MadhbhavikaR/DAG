#!/usr/bin/env python3
"""Build and validate the installable Calibre plugin archive from src/."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PROJECT = "annas-archieve-callibre-plugin"
REQUIRED_FILES = (
    "__init__.py",
    "annas_archive.py",
    "config.py",
    "constants.py",
    "plugin-import-name-store_annas_archive.txt",
)


def metadata_version() -> tuple[int, int, int]:
    """Read the version tuple from the Calibre metadata class."""
    metadata_path = SRC / "__init__.py"
    try:
        tree = ast.parse(metadata_path.read_text(encoding="utf-8"), filename=str(metadata_path))
    except SyntaxError as exc:
        raise ValueError(f"Cannot parse Calibre metadata in {metadata_path}: {exc}") from exc

    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "AnnasArchiveStore":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "version" for target in statement.targets):
                continue
            try:
                value = ast.literal_eval(statement.value)
            except (ValueError, TypeError) as exc:
                raise ValueError("Plugin metadata version must be a literal integer tuple") from exc
            if (
                not isinstance(value, tuple)
                or len(value) != 3
                or not all(isinstance(item, int) and not isinstance(item, bool) for item in value)
            ):
                raise ValueError("Plugin metadata version must be a three-part integer tuple")
            return value
    raise ValueError("Could not find AnnasArchiveStore.version in src/__init__.py")


def read_version() -> str:
    """Read the installable plugin version from Calibre metadata."""
    return ".".join(str(part) for part in metadata_version())


def archive_path(version: str) -> Path:
    """Return the default versioned archive path."""
    return ROOT / "dist" / f"{PROJECT}-v{version}.zip"


def build(path: Path, check_only: bool = False, version_override: str | None = None) -> None:
    """Build an installable ZIP with src/ contents at its root."""
    if version_override and not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version_override):
        raise ValueError(f"Release version must be MAJOR.MINOR.PATCH; got {version_override!r}")

    missing = [name for name in REQUIRED_FILES if not (SRC / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required plugin files under src/: " + ", ".join(missing))

    if check_only:
        if not path.is_file():
            raise FileNotFoundError(f"Archive does not exist: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            for name in REQUIRED_FILES:
                source = SRC / name
                if name == "__init__.py" and version_override:
                    text = source.read_text(encoding="utf-8")
                    parts = tuple(int(part) for part in version_override.split("."))
                    replacement = "version = (" + ", ".join(str(part) for part in parts) + ")"
                    text, count = re.subn(
                        r"(?<![A-Za-z0-9_])version\s*=\s*\([0-9]+\s*,\s*[0-9]+\s*,\s*[0-9]+\)",
                        replacement,
                        text,
                    )
                    if count != 1:
                        raise ValueError("Could not inject release version into AnnasArchiveStore.version")
                    archive.writestr(name, text.encode("utf-8"))
                else:
                    archive.write(source, arcname=name)

    with ZipFile(path) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member:
            raise ValueError(f"ZIP integrity check failed at member: {corrupt_member}")
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(REQUIRED_FILES):
            raise ValueError(f"Unexpected ZIP entries: {names!r}")

    print(("Validated " if check_only else "Built and validated ") + str(path.relative_to(ROOT)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the default archive without rebuilding it")
    parser.add_argument("--version-only", action="store_true", help="print the version from src/__init__.py")
    parser.add_argument("--version", help="override packaged plugin version (MAJOR.MINOR.PATCH)")
    parser.add_argument("--archive", type=Path, help="optional archive output path")
    args = parser.parse_args()

    try:
        if args.version_only:
            print(read_version())
            return 0
        version = args.version or read_version()
        path = args.archive or archive_path(version)
        if not path.is_absolute():
            path = ROOT / path
        build(path, check_only=args.check, version_override=args.version)
    except (FileNotFoundError, OSError, ValueError, BadZipFile) as exc:
        print(f"Plugin packaging failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
