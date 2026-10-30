from __future__ import annotations

import json
import os
import re
from pathlib import Path
from .config import Config
from .errors import ErrorHandler
from .filesystem import FileSystemManager
from .hashing import HashEngine
from .indexing import IndexManager
from .mutations import MutationFactory
from .output import Output
from .text_utils import TextUtils


class FileEditor:
    def __init__(self, path: Path, output: Output):
        self.path = path
        self.output = output

    def create(self, content: str | None) -> None:
        if self.path.exists():
            ErrorHandler.fail("FILE_EXISTS", f"File '{self.path}' already exists.", "Use rewrite to replace it, or edit it after search/read.")
        if content is None:
            ErrorHandler.fail("MISSING_CONTENT", "No initial content was supplied.", "Pipe content to stdin.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = TextUtils.normalize_content(content, "\n")
        try:
            with self.path.open("xb") as handle:
                handle.write(text.encode(Config.UTF8))
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            ErrorHandler.fail("CREATE_FAILED", f"Unable to create '{self.path}': {exc}")
        FileSystemManager._fsync_directory(self.path.parent)
        lines = text.splitlines(keepends=True)
        IndexManager.get_current_index(self.path, text.encode(Config.UTF8), lines, "\n")
        self.output.ok({"operation": "create", "lines": len(lines)})

    def rewrite(self, content: str | None) -> None:
        """Replace the whole file, avoiding a fragile first-hash..last-hash range edit."""

        if content is None:
            ErrorHandler.fail("MISSING_INPUT", "No replacement content was supplied.", "Pipe content to stdin.")
        text = TextUtils.normalize_content(content, "\n")
        lines = text.splitlines(keepends=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        FileSystemManager.atomic_replace(self.path, text)
        IndexManager.get_current_index(self.path, text.encode(Config.UTF8), lines, "\n")
        self.output.ok({"operation": "rewrite", "lines": len(lines)})

    def _load(self):
        lines, text, newline, raw = FileSystemManager.read_file(self.path)
        index = IndexManager.get_current_index(self.path, raw, lines, newline)
        return lines, text, newline, raw, index

    def read(self, target_hash: str | None, before: int | None, after: int | None) -> None:
        lines, _, _, raw, index = self._load()
        hashes = index["sequence"]

        if target_hash is None:
            if before is not None or after is not None:
                ErrorHandler.fail("HASH_REQUIRED", "A HASH is required when context counts are supplied.")
            if not lines:
                self.output.ok({"operation": "read", "lines": 0, "context": []})
                return
            # Default full-file read is deliberately compact and capped.
            context = self._context_records(lines, hashes, 0, len(lines) - 1)
            truncated = len(context) < len(lines)
            self.output.ok({
                "operation": "read",
                "lines": len(lines),
                "truncated": truncated,
                "context": context,
            })
            return

        target_hash = HashEngine.validate(target_hash)
        target = HashEngine.resolve_unique(index, target_hash, self.path)
        before = Config.DEFAULT_PREVIOUS if before is None else before
        after = Config.DEFAULT_NEXT if after is None else after
        self._validate_context(before, after)
        context = self._context_records(lines, hashes, max(0, target - before), min(len(lines) - 1, target + after))
        self.output.ok({
            "operation": "read",
            "anchor": target_hash,
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
            ErrorHandler.fail(
                "EMPTY_QUERY",
                "Search query is empty.",
                "Pipe the text to search for into stdin.",
            )
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
            # Literal substring search is the safe/default operation for SLMs.
            matches_line = lambda body: query in body

        lines, _, _, _, index = self._load()
        hashes = index["sequence"]

        matched_indices = [
            idx for idx, line in enumerate(lines)
            if matches_line(TextUtils.line_body(line))
        ]

        returned_indices = matched_indices[:limit]
        # Only the matched line is returned; use READ for surrounding context.
        matches = [
            {
                "hash": hashes[idx],
                "line": idx + 1,
                "text": TextUtils.clip(TextUtils.line_body(lines[idx])),
            }
            for idx in returned_indices
        ]

        self.output.ok({
            "operation": "search",
            "count": len(matched_indices),
            "truncated": len(matched_indices) > limit,
            "matches": matches,
        })

    def mutate(self, name: str, start_hash: str, end_hash: str | None, content: str | None, position: str | None = None) -> None:
        start_hash = HashEngine.validate(start_hash)
        if end_hash is not None:
            end_hash = HashEngine.validate(end_hash)

        old_lines, _, newline, old_raw, old_index = self._load()
        if not old_lines:
            ErrorHandler.fail("EMPTY_FILE", f"File '{self.path}' is empty.", "Create/populate the file before editing.")

        start = HashEngine.resolve_unique(old_index, start_hash, self.path)
        end = start if end_hash is None else HashEngine.resolve_unique(old_index, end_hash, self.path)

        if end < start:
            ErrorHandler.fail("INVALID_RANGE", "END_HASH occurs before START_HASH.", "Use START_HASH then END_HASH in file order.")

        if name == "insert" and end_hash is not None:
            ErrorHandler.fail("INSERT_RANGE", "INSERT accepts one anchor, not a range.", "Use insert before|after FILE HASH.")

        command = MutationFactory.get(name, position)
        new_lines, target, action = command.execute(old_lines, start, end, content, newline)

        new_hashes = HashEngine.generate_all(new_lines)
        HashEngine.enforce_uniqueness(new_hashes)
        new_text = "".join(new_lines)
        new_raw = new_text.encode(Config.UTF8)

        try:
            current_raw = self.path.read_bytes()
        except OSError as exc:
            ErrorHandler.fail("VERIFY_FAILED", f"Unable to verify '{self.path}': {exc}")
        if current_raw != old_raw:
            ErrorHandler.fail(
                "STALE_FILE",
                f"File '{self.path}' changed while the edit was being prepared.",
                "Read/search again and retry with a current hash.",
            )

        FileSystemManager.atomic_replace(self.path, new_text)
        IndexManager.get_current_index(self.path, new_raw, new_lines, newline)

        result = {
            "operation": action,
            "lines_changed": (end - start + 1) if action != "insert" else 0,
            "lines_after": len(new_lines),
        }

        if target >= 0:
            start_ctx = max(0, target - Config.DEFAULT_PREVIOUS)
            end_ctx = min(len(new_lines) - 1, target + Config.DEFAULT_NEXT)
            result["anchor"] = new_hashes[target]
            result["line"] = target + 1
            result["context"] = self._context_records(new_lines, new_hashes, start_ctx, end_ctx)
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

    @staticmethod
    def _context_records(lines, hashes, start, end):
        records = []
        total_chars = 0
        for idx in range(start, end + 1):
            body = TextUtils.clip(TextUtils.line_body(lines[idx]))
            record = {"offset": idx - start, "hash": hashes[idx], "text": body}
            encoded_size = len(json.dumps(record, ensure_ascii=False))
            if records and total_chars + encoded_size > Config.MAX_CONTEXT_CHARS:
                break
            records.append(record)
            total_chars += encoded_size
        return records
