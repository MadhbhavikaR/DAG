from __future__ import annotations

import hashlib
import re
from pathlib import Path
from .config import Config
from .errors import ErrorHandler
from .text_utils import TextUtils


class HashEngine:
    @staticmethod
    def generate_all(lines: list[str]) -> list[str]:
        # Keep the established 3-line-window + line-number anchor semantics.
        # The tool's stale-file SHA protects against using anchors from an older
        # file version. A future stable-anchor migration can be done explicitly.
        result: list[str] = []
        length = len(lines)

        def get_line(i: int) -> str:
            if i < 0:
                return Config.START_MARKER
            if i >= length:
                return Config.END_MARKER
            return TextUtils.line_body(lines[i])

        for i in range(length):
            payload = f"{i}{get_line(i)}{get_line(i - 1)}{get_line(i + 1)}"
            result.append(
                hashlib.sha256(payload.encode(Config.UTF8)).hexdigest()[:Config.HASH_LENGTH]
            )
        return result

    @staticmethod
    def validate(value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{Config.HASH_LENGTH}}}", value):
            ErrorHandler.fail(
                "INVALID_HASH",
                f"Invalid hash '{value}'.",
                "Use the exact 8-character lowercase hash returned by read or search.",
            )
        return value

    @staticmethod
    def resolve_unique(index: dict, value: str, path: Path) -> int:
        matches = index.get("lines", {}).get(value)
        if not matches:
            ErrorHandler.fail(
                "STALE_HASH",
                f"Hash '{value}' was not found in '{path}'.",
                "Read/search the file again and use a current hash.",
            )
        if len(matches) != 1:
            ErrorHandler.fail(
                "AMBIGUOUS_HASH",
                f"Hash '{value}' matches multiple lines in '{path}'.",
                "Use a different anchor.",
            )
        return matches[0]["index"]

    @staticmethod
    def enforce_uniqueness(hashes: list[str]) -> None:
        seen: set[str] = set()
        for value in hashes:
            if value in seen:
                ErrorHandler.fail(
                    "HASH_COLLISION",
                    f"Hash '{value}' would identify multiple lines after the mutation.",
                    "Choose different content so every line has a unique hash.",
                )
            seen.add(value)
