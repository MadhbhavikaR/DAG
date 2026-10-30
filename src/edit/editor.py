"""Application service coordinating safe, anchor-based file operations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorHandler
from .filesystem import FileSystemManager
from .hashing import HashEngine
from .indexing import IndexManager
from .mutations import MutationRegistry
from .output import Output
from .ports import FileSystemPort, HashPort, IndexPort, MutationProvider, OutputPort, TextPort
from .text_utils import TextUtils


class FileEditor:
    """Coordinate file editing while delegating policies to injected services."""

    def __init__(
        self,
        path: Path,
        output: OutputPort,
        *,
        filesystem: FileSystemPort | None = None,
        hashing: HashPort | None = None,
        indexing: IndexPort | None = None,
        mutations: MutationProvider | None = None,
        text: TextPort | None = None,
    ) -> None:
        self.path = path
        self.output = output
        self.filesystem = filesystem or FileSystemManager()
        self.hashing = hashing or HashEngine()
        self.indexing = indexing or IndexManager()
        self.mutations = mutations or MutationRegistry()
        self.text = text or TextUtils()

    def create(self, content: str | None) -> None:
        if self.path.exists():
            ErrorHandler.fail(
                "FILE_EXISTS",
                f"File '{self.path}' already exists.",
                "Use rewrite to replace it, or edit it after search/read.",
            )
        if content is None:
            ErrorHandler.fail("MISSING_CONTENT", "No initial content was supplied.", "Pipe content to stdin.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalized = self.text.normalize_content(content, "\\n")
        raw = normalized.encode(Config.UTF8)
        self.filesystem.create_file(self.path, raw)
        lines = normalized.splitlines(keepends=True)
        self.indexing.get_current_index(self.path, raw, lines, "\\n")
        self.output.ok({"operation": "create", "lines": len(lines)})

    def rewrite(self, content: str | None) -> None:
        """Replace the entire file atomically."""
        if content is None:
            ErrorHandler.fail("MISSING_INPUT", "No replacement content was supplied.", "Pipe content to stdin.")

        normalized = self.text.normalize_content(content, "\\n")
        lines = normalized.splitlines(keepends=True)
        raw = normalized.encode(Config.UTF8)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.filesystem.atomic_replace(self.path, normalized)
        self.indexing.get_current_index(self.path, raw, lines, "\\n")
        self.output.ok({"operation": "rewrite", "lines": len(lines)})

    def _load(self) -> tuple[list[str], str, str, bytes, dict[str, Any]]:
        lines, text, newline, raw = self.filesystem.read_file(self.path)
        index = self.indexing.get_current_index(self.path, raw, lines, newline)
        return lines, text, newline, raw, index

    def read(self, target_hash: str | None, before: int | None, after: int | None) -> None:
        lines, _, _, _, index = self._load()
        hashes = index["sequence"]

        if target_hash is None:
            if before is not None or after is not None:
                ErrorHandler.fail("HASH_REQUIRED", "A HASH is required when context counts are supplied.")
            if not lines:
                self.output.ok({"operation": "read", "lines": 0, "context": []})
                return
            context = self._context_records(lines, hashes, 0, len(lines) - 1)
            self.output.ok({
                "operation": "read",
                "lines": len(lines),
                "truncated": len(context) < len(lines),
                "context": context,
            })
            return

        validated_hash = self.hashing.validate(target_hash)
        target = self.hashing.resolve_unique(index, validated_hash, self.path)
        previous = Config.DEFAULT_PREVIOUS if before is None else before
        following = Config.DEFAULT_NEXT if after is None else after
        self._validate_context(previous, following)
        context = self._context_records(
            lines, hashes, max(0, target - previous), min(len(lines) - 1, target + following)
        )
        self.output.ok({
            "operation": "read",
            "anchor": validated_hash,
            "line": target + 1,
            "context": context,
        })

    def search(
        self,
        query: str,
        regex: bool = False,
        limit: int = 5,
        before: int = Config.DEFAULT_PREVIOUS,
        after: int = Config.DEFAULT_NEXT,
    ) -> None:
        if not query:
            ErrorHandler.fail("EMPTY_QUERY", "Search query is empty.", "Pipe the text to search for into stdin.")
        if limit < 1:
            ErrorHandler.fail("INVALID_LIMIT", "SEARCH limit must be at least 1.")
        self._validate_context(before, after)

        if regex:
            try:
                matcher = re.compile(query)
            except re.error as exc:
                ErrorHandler.fail("INVALID_REGEX", f"Invalid regular expression: {exc}")
            matches_line = lambda body: bool(matcher.search(body))
        else:
            matches_line = lambda body: query in body

        lines, _, _, _, index = self._load()
        hashes = index["sequence"]
        matched_indices = [
            index for index, line in enumerate(lines)
            if matches_line(self.text.line_body(line))
        ]
        matches = [
            {
                "hash": hashes[index],
                "line": index + 1,
                "text": self.text.clip(self.text.line_body(lines[index])),
            }
            for index in matched_indices[:limit]
        ]
        self.output.ok({
            "operation": "search",
            "count": len(matched_indices),
            "truncated": len(matched_indices) > limit,
            "matches": matches,
        })

    def mutate(
        self,
        name: str,
        start_hash: str,
        end_hash: str | None,
        content: str | None,
        position: str | None = None,
    ) -> None:
        start_anchor = self.hashing.validate(start_hash)
        end_anchor = self.hashing.validate(end_hash) if end_hash is not None else None

        old_lines, _, newline, old_raw, old_index = self._load()
        if not old_lines:
            ErrorHandler.fail("EMPTY_FILE", f"File '{self.path}' is empty.", "Create/populate the file before editing.")

        start = self.hashing.resolve_unique(old_index, start_anchor, self.path)
        end = start if end_anchor is None else self.hashing.resolve_unique(old_index, end_anchor, self.path)
        if end < start:
            ErrorHandler.fail("INVALID_RANGE", "END_HASH occurs before START_HASH.", "Use START_HASH then END_HASH in file order.")
        if name == "insert" and end_anchor is not None:
            ErrorHandler.fail("INSERT_RANGE", "INSERT accepts one anchor, not a range.", "Use insert before|after FILE HASH.")

        command = self.mutations.get(name, position)
        new_lines, target, action = command.execute(old_lines, start, end, content, newline)
        new_hashes = self.hashing.generate_all(new_lines)
        self.hashing.enforce_uniqueness(new_hashes)
        new_text = "".join(new_lines)
        new_raw = new_text.encode(Config.UTF8)

        try:
            current_raw = self.filesystem.read_bytes(self.path)
        except OSError as exc:
            ErrorHandler.fail("VERIFY_FAILED", f"Unable to verify '{self.path}': {exc}")
        if current_raw != old_raw:
            ErrorHandler.fail(
                "STALE_FILE",
                f"File '{self.path}' changed while the edit was being prepared.",
                "Read/search again and retry with a current hash.",
            )

        self.filesystem.atomic_replace(self.path, new_text)
        self.indexing.get_current_index(self.path, new_raw, new_lines, newline)
        result: dict[str, Any] = {
            "operation": action,
            "lines_changed": end - start + 1 if action != "insert" else 0,
            "lines_after": len(new_lines),
        }

        if target >= 0:
            context_start = max(0, target - Config.DEFAULT_PREVIOUS)
            context_end = min(len(new_lines) - 1, target + Config.DEFAULT_NEXT)
            result["anchor"] = new_hashes[target]
            result["line"] = target + 1
            result["context"] = self._context_records(
                new_lines, new_hashes, context_start, context_end
            )
        else:
            result["anchor"] = None
            result["context"] = []
        self.output.ok(result)

    @staticmethod
    def _validate_context(before: int, after: int) -> None:
        if before < 0 or after < 0:
            ErrorHandler.fail("INVALID_CONTEXT", "Context counts cannot be negative.")
        if before + after + 1 > Config.MAX_CONTEXT_LINES:
            ErrorHandler.fail(
                "CONTEXT_TOO_LARGE",
                f"Requested context exceeds {Config.MAX_CONTEXT_LINES} lines.",
                f"Use at most {Config.MAX_CONTEXT_LINES - 1} surrounding lines.",
            )

    def _context_records(
        self, lines: list[str], hashes: list[str], start: int, end: int
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        total_chars = 0
        for index in range(start, end + 1):
            body = self.text.clip(self.text.line_body(lines[index]))
            record = {"offset": index - start, "hash": hashes[index], "text": body}
            encoded_size = len(json.dumps(record, ensure_ascii=False))
            if records and total_chars + encoded_size > Config.MAX_CONTEXT_CHARS:
                break
            records.append(record)
            total_chars += encoded_size
        return records
