#!/usr/bin/env python3
"""
edit.py — Context-Anchored LLM/SLM File Editor
==============================================

Designed for small instruction-following models with limited context.

DEFAULT OUTPUT
--------------
JSON is the default because models should not have to parse prose.
Use --human for human-readable output.

CONTENT
-------
Mutation and search content are read from stdin. Pipe exact UTF-8 content:

    printf '%s\n' 'line 1' 'line 2' | ./edit.py replace app.py HASH

stdin is the single multiline transport, so code and multiline content do not
need shell escaping.

CORE WORKFLOW
-------------
    search -> read context -> edit -> verify

Never invent a hash. Hashes returned by search/read are anchors for the
current file version only.

COMMANDS
--------
    create FILE
    read FILE [HASH [BEFORE AFTER]]
    search FILE [--regex] [--limit N] [--before N] [--after N]
    replace FILE START_HASH [END_HASH]
    insert before|after FILE HASH
    delete FILE START_HASH [END_HASH]
    prompt

Range replacement/deletion uses START_HASH and END_HASH, inclusive.
If END_HASH is omitted, replace/delete affects one line.

The SLM prompt is available with:
    ./edit.py prompt
or:
    ./edit.py --prompt

Agent output is compact JSON by default. Use --human only when a person is
interacting directly with the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import NoReturn


class Config:
    HASH_LENGTH = 8
    START_MARKER = "[START]"
    END_MARKER = "[END]"
    DEFAULT_PREVIOUS = 1
    DEFAULT_NEXT = 1
    MAX_CONTEXT_LINES = 12
    MAX_CONTEXT_CHARS = 1200
    MAX_OUTPUT_CHARS = 4000
    # Long lines are clipped in output so one response cannot flood a small context window.
    MAX_LINE_CHARS = 160
    INDEX_VERSION = 8
    INDEX_SUFFIX = ".ctxidx"
    INDEX_DIR_NAME = "edit.py"
    TRANSACTION_MARKER = ".ctxnew."
    UTF8 = "utf-8"


class ToolError(Exception):
    def __init__(self, code: str, message: str, solution: str | None = None) -> None:
        self.code = code
        self.message = message
        self.solution = solution
        super().__init__(message)


class ErrorHandler:
    @staticmethod
    def fail(code: str, message: str, solution: str | None = None) -> NoReturn:
        raise ToolError(code, message, solution)


class AgentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Keep argparse failures machine-readable too.
        raise ToolError("ARGUMENT_ERROR", message, "Run './edit.py prompt' for the compact tool protocol.")


class TextUtils:
    @staticmethod
    def detect_newline(text: str) -> str:
        for i, char in enumerate(text):
            if char == "\r":
                return "\r\n" if i + 1 < len(text) and text[i + 1] == "\n" else "\r"
            if char == "\n":
                return "\n"
        return "\n"

    @staticmethod
    def normalize_content(content: str, newline: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)
        if not normalized:
            return ""
        if not normalized.endswith(("\n", "\r")):
            normalized += newline
        return normalized

    @staticmethod
    def line_body(line: str) -> str:
        return line.rstrip("\r\n")

    @staticmethod
    def clip(body: str) -> str:
        """Clip an emitted line so a single response stays small-context friendly."""

        if len(body) <= Config.MAX_LINE_CHARS:
            return body
        return body[: Config.MAX_LINE_CHARS] + "\u2026"


class FileSystemManager:
    @staticmethod
    def read_file(path: Path) -> tuple[list[str], str, str, bytes]:
        try:
            st = path.stat()
        except FileNotFoundError:
            ErrorHandler.fail(
                "FILE_NOT_FOUND", f"File '{path}' does not exist.",
                f"Create it with: ./edit.py create {path} < stdin",
            )
        except OSError as exc:
            ErrorHandler.fail("FILE_ACCESS", f"Unable to access '{path}': {exc}")

        if not stat.S_ISREG(st.st_mode):
            ErrorHandler.fail("NOT_A_FILE", f"'{path}' is not a regular file.")

        try:
            raw = path.read_bytes()
            text = raw.decode(Config.UTF8)
        except UnicodeDecodeError as exc:
            ErrorHandler.fail("INVALID_UTF8", f"File '{path}' is not valid UTF-8: {exc}")
        except OSError as exc:
            ErrorHandler.fail("READ_FAILED", f"Unable to read '{path}': {exc}")

        return text.splitlines(keepends=True), text, TextUtils.detect_newline(text), raw

    @staticmethod
    def atomic_replace(path: Path, new_text: str) -> None:
        temporary = path.with_name(
            f".{path.name}{Config.TRANSACTION_MARKER}{secrets.token_hex(8)}"
        )
        try:
            with temporary.open("wb") as handle:
                handle.write(new_text.encode(Config.UTF8))
                handle.flush()
                os.fsync(handle.fileno())
            try:
                mode = stat.S_IMODE(path.stat().st_mode)
            except FileNotFoundError:
                mode = None
            except OSError as exc:
                ErrorHandler.fail("PERMISSION_UPDATE_FAILED", f"Unable to preserve permissions: {exc}")
            if mode is not None:
                try:
                    os.chmod(temporary, mode)
                except OSError as exc:
                    ErrorHandler.fail("PERMISSION_UPDATE_FAILED", f"Unable to preserve permissions: {exc}")
            os.replace(temporary, path)
            FileSystemManager._fsync_directory(path.parent)
        except ToolError:
            raise
        except OSError as exc:
            try:
                temporary.unlink()
            except OSError:
                pass
            ErrorHandler.fail(
                "COMMIT_FAILED",
                f"Unable to commit changes to '{path}': {exc}",
                "Check that the file and parent directory are writable.",
            )
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        flags = getattr(os, "O_DIRECTORY", 0)
        try:
            fd = os.open(str(directory), os.O_RDONLY | flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    @staticmethod
    def cleanup_transactions(path: Path) -> None:
        try:
            for candidate in path.parent.glob(f".{path.name}{Config.TRANSACTION_MARKER}*"):
                try:
                    candidate.unlink()
                except OSError:
                    pass
        except OSError:
            pass


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


class IndexManager:
    @staticmethod
    def get_index_path(path: Path) -> Path:
        canonical = str(path.resolve())
        key = hashlib.sha256(canonical.encode(Config.UTF8)).hexdigest()
        directory = Path(tempfile.gettempdir()) / Config.INDEX_DIR_NAME
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.chmod(directory, 0o700)
            except OSError:
                pass
        except OSError as exc:
            ErrorHandler.fail(
                "INDEX_DIR_FAILED",
                f"Unable to create editor index directory '{directory}': {exc}",
                "Check that the OS temporary directory is writable.",
            )
        return directory / f"{key}{Config.INDEX_SUFFIX}"

    @staticmethod
    def _sha256(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def build_locations(lines: list[str]) -> tuple[list[int], list[int]]:
        offsets: list[int] = []
        lengths: list[int] = []
        offset = 0
        for line in lines:
            length = len(line.encode(Config.UTF8))
            offsets.append(offset)
            lengths.append(length)
            offset += length
        return offsets, lengths

    @classmethod
    def get_current_index(cls, path: Path, raw: bytes, lines: list[str], newline: str) -> dict:
        cached = cls._load_index(path)
        if cls._is_valid(cached, raw, lines):
            return cached

        hashes = HashEngine.generate_all(lines)
        offsets, lengths = cls.build_locations(lines)
        st = path.stat()
        lines_map: dict[str, list[dict]] = {}
        for idx, value in enumerate(hashes):
            lines_map.setdefault(value, []).append(
                {"index": idx, "offset": offsets[idx], "length": lengths[idx]}
            )

        data = {
            "version": Config.INDEX_VERSION,
            "size": len(raw),
            "mtime_ns": st.st_mtime_ns,
            "file_sha256": cls._sha256(raw),
            "newline": newline,
            "sequence": hashes,
            "lines": lines_map,
        }
        cls._atomic_write(path, data)
        return data

    @classmethod
    def _load_index(cls, path: Path) -> dict | None:
        try:
            with cls.get_index_path(path).open("r", encoding=Config.UTF8) as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else None
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return None

    @classmethod
    def _is_valid(cls, index: dict | None, raw: bytes, lines: list[str]) -> bool:
        if not index or index.get("version") != Config.INDEX_VERSION:
            return False
        if index.get("size") != len(raw) or index.get("file_sha256") != cls._sha256(raw):
            return False
        sequence = index.get("sequence")
        return isinstance(sequence, list) and len(sequence) == len(lines)

    @classmethod
    def _atomic_write(cls, path: Path, data: dict) -> None:
        index_file = cls.get_index_path(path)
        temporary = index_file.with_name(f".{index_file.name}.tmp.{secrets.token_hex(8)}")
        try:
            encoded = (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode(Config.UTF8)
            with temporary.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, index_file)
        except OSError:
            # Index is a cache. Editing remains valid without it.
            pass
        finally:
            try:
                temporary.unlink()
            except OSError:
                pass


class MutationCommand(ABC):
    @abstractmethod
    def execute(
        self, lines: list[str], start: int, end: int, content: str | None, newline: str
    ) -> tuple[list[str], int, str]:
        pass


class ReplaceCommand(MutationCommand):
    def execute(self, lines, start, end, content, newline):
        if content is None:
            ErrorHandler.fail("MISSING_CONTENT", "No replacement content was supplied.", "Pipe the replacement block to stdin.")
        replacement = TextUtils.normalize_content(content, newline).splitlines(keepends=True)
        new_lines = lines[:start] + replacement + lines[end + 1:]
        target = start if replacement else min(start, len(new_lines) - 1)
        return new_lines, target, "replace"


class InsertCommand(MutationCommand):
    def __init__(self, position: str):
        if position not in {"before", "after"}:
            ErrorHandler.fail("INVALID_POSITION", "INSERT position must be 'before' or 'after'.")
        self.position = position

    def execute(self, lines, start, end, content, newline):
        if content is None:
            ErrorHandler.fail("MISSING_CONTENT", "No insertion content was supplied.", "Pipe the insertion block to stdin.")
        inserted = TextUtils.normalize_content(content, newline).splitlines(keepends=True)
        if not inserted:
            ErrorHandler.fail("EMPTY_CONTENT", "Insertion content is empty.", "Pipe at least one line to stdin.")
        if self.position == "before":
            new_lines = lines[:start] + inserted + lines[start:]
            target = start + len(inserted)
        else:
            new_lines = lines[:end + 1] + inserted + lines[end + 1:]
            target = end + len(inserted)
        return new_lines, target, "insert"


class DeleteCommand(MutationCommand):
    def execute(self, lines, start, end, content, newline):
        new_lines = lines[:start] + lines[end + 1:]
        target = min(start, len(new_lines) - 1) if new_lines else -1
        return new_lines, target, "delete"


class MutationFactory:
    @staticmethod
    def get(name: str, position: str | None = None) -> MutationCommand:
        if name == "replace":
            return ReplaceCommand()
        if name == "delete":
            return DeleteCommand()
        if name == "insert":
            return InsertCommand(position or "")
        ErrorHandler.fail("UNSUPPORTED_COMMAND", f"Unsupported command '{name}'.")


class FileEditor:
    def __init__(self, path: Path, output: "Output"):
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


class Output:
    def __init__(self, human: bool):
        self.human = human

    def ok(self, data: dict) -> None:
        if self.human:
            self._human_ok(data)
        else:
            self._json({"ok": True, **data})

    def error(self, exc: ToolError) -> None:
        payload = {"ok": False, "error": exc.code, "message": exc.message}
        if exc.solution:
            payload["action"] = exc.solution
        if self.human:
            print(f"ERROR [{exc.code}]: {exc.message}", file=sys.stderr)
            if exc.solution:
                print(f"Solution: {exc.solution}", file=sys.stderr)
        else:
            self._json(payload, stderr=True)

    @staticmethod
    def _json(data: dict, stderr: bool = False) -> None:
        stream = sys.stderr if stderr else sys.stdout
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")), file=stream)

    @staticmethod
    def _human_ok(data: dict) -> None:
        op = data.get("operation", "ok")
        print(f"OK: {op}")
        for key, value in data.items():
            if key == "operation":
                continue
            if key == "context":
                print("CONTEXT:")
                for row in value:
                    print(f"{row['offset']:+d} {row['hash']}: {row['text']}")
            elif key == "matches":
                for row in value:
                    print(f"{row['line']}: {row['hash']}: {row['text']}")
            else:
                print(f"{key}: {value}")


class CLI:
    PROMPT = """edit.py PROTOCOL (one text file, JSON out; --human for people)
stdin carries content and search text.

CREATE   printf '%s\\n' 'l1' 'l2' | ./edit.py create FILE      (fails if FILE exists)
REWRITE  printf '%s\\n' 'l1' 'l2' | ./edit.py rewrite FILE     (replaces all of FILE)
SEARCH   printf '%s' 'text' | ./edit.py search FILE      (literal; --regex opt-in; max 5 hits)
READ     ./edit.py read FILE HASH [BEFORE AFTER]
REPLACE  printf '%s\\n' 'new' | ./edit.py replace FILE HASH
         printf '%s\\n' 'a' 'b' | ./edit.py replace FILE START..END
INSERT   printf '%s\\n' 'new' | ./edit.py insert before|after FILE HASH
DELETE   ./edit.py delete FILE HASH        ./edit.py delete FILE START..END

HASH comes only from search/read output. START..END is inclusive. Never invent a hash.
SEARCH returns just the matched lines; use READ for surrounding context.
Long lines are clipped with an ellipsis.

WORKFLOW  search -> read if needed -> edit -> use the returned hashes.

JSON INPUT  ./edit.py --json-input
{"command":"replace","file":"app.py","target":"HASH..HASH","input":"new text\\n"}
commands: create, rewrite, read, search, replace, insert, delete

ERRORS
STALE_HASH / STALE_FILE  -> search or read again
AMBIGUOUS_HASH           -> pick another observed hash
HASH_COLLISION           -> change the new content
MISSING_INPUT            -> provide stdin input
"""

    @staticmethod
    def read_stdin_if_available() -> str | None:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        try:
            return sys.stdin.read()
        except OSError as exc:
            ErrorHandler.fail("STDIN_FAILED", f"Unable to read stdin: {exc}")

    @staticmethod
    def split_target(target: str):
        if not target:
            ErrorHandler.fail("MISSING_TARGET", "A target hash is required.")
        parts = target.split("..")
        if len(parts) > 2 or not all(parts):
            ErrorHandler.fail("INVALID_TARGET", "Target must be HASH or START_HASH..END_HASH.")
        return parts[0], parts[1] if len(parts) == 2 else None

    @staticmethod
    def build_parser():
        parser = AgentArgumentParser(
            prog="./edit.py",
            description="Single-file create/search/read/replace/insert/delete tool for LLM/SLM agents.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--human", action="store_true", help="Human-readable output. JSON is default.")
        parser.add_argument("--prompt", action="store_true", help="Print the compact SLM protocol.")
        parser.add_argument("--json-input", action="store_true", help="Read one JSON request object from stdin.")
        sub = parser.add_subparsers(dest="command")

        p=sub.add_parser("create", help="Create FILE from stdin."); p.add_argument("file")
        p=sub.add_parser("rewrite", help="Replace all of FILE from stdin."); p.add_argument("file")
        p=sub.add_parser("read", help="Read bounded file/context."); p.add_argument("file"); p.add_argument("hash",nargs="?"); p.add_argument("before",nargs="?",type=int,default=None); p.add_argument("after",nargs="?",type=int,default=None)
        p=sub.add_parser("search", help="Search stdin text in FILE."); p.add_argument("file"); p.add_argument("--regex",action="store_true"); p.add_argument("--limit",type=int,default=5); p.add_argument("--before",type=int,default=Config.DEFAULT_PREVIOUS); p.add_argument("--after",type=int,default=Config.DEFAULT_NEXT)
        p=sub.add_parser("replace", help="Replace HASH or HASH..HASH using stdin."); p.add_argument("file"); p.add_argument("target")
        p=sub.add_parser("insert", help="Insert stdin content before or after HASH."); p.add_argument("position",choices=("before","after")); p.add_argument("file"); p.add_argument("hash")
        p=sub.add_parser("delete", help="Delete HASH or HASH..HASH."); p.add_argument("file"); p.add_argument("target")
        sub.add_parser("prompt", help="Print the compact SLM protocol.")
        return parser

    @classmethod
    def json_input(cls, output):
        raw=cls.read_stdin_if_available()
        if raw is None: ErrorHandler.fail("MISSING_JSON","JSON request must be supplied on stdin.")
        try: req=json.loads(raw)
        except json.JSONDecodeError as exc: ErrorHandler.fail("INVALID_JSON",f"Invalid JSON: {exc}")
        if not isinstance(req,dict): ErrorHandler.fail("INVALID_JSON","JSON request must be an object.")
        command=req.get("command")
        if command not in {"create","rewrite","read","search","replace","insert","delete"}: ErrorHandler.fail("INVALID_COMMAND","command must be create, rewrite, read, search, replace, insert, or delete.")
        filename=req.get("file")
        if not isinstance(filename,str) or not filename: ErrorHandler.fail("MISSING_FILE","file is required.")
        path=Path(filename); FileSystemManager.cleanup_transactions(path); editor=FileEditor(path,output); value=req.get("input")
        if value is not None and not isinstance(value,str): ErrorHandler.fail("INVALID_INPUT","input must be a string.")
        if command=="rewrite": editor.rewrite(value)
        elif command=="create":
            if value is None: ErrorHandler.fail("MISSING_INPUT","Create content must be in input.")
            editor.create(value)
        elif command=="read": editor.read(req.get("hash"),cls.json_int(req, "before"),cls.json_int(req, "after"))
        elif command=="search": editor.search(value or "",bool(req.get("regex",False)),cls.json_int(req, "limit", 5),cls.json_int(req, "before", Config.DEFAULT_PREVIOUS),cls.json_int(req, "after", Config.DEFAULT_NEXT))
        elif command=="replace":
            a,b=cls.split_target(str(req.get("target","")))
            if value is None: ErrorHandler.fail("MISSING_INPUT","Replacement content must be in input.")
            editor.mutate("replace",a,b,value)
        elif command=="insert":
            if value is None: ErrorHandler.fail("MISSING_INPUT","Insertion content must be in input.")
            editor.mutate("insert",str(req.get("hash","")),None,value,str(req.get("position","")))
        else:
            a,b=cls.split_target(str(req.get("target",""))); editor.mutate("delete",a,b,None)
        return 0

    @staticmethod
    def json_int(request: dict, name: str, default: int | None = None) -> int | None:
        value = request.get(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            ErrorHandler.fail("INVALID_NUMBER", f"'{name}' must be an integer.", f"Set '{name}' to a whole number.")
        try:
            return int(value)
        except (TypeError, ValueError):
            ErrorHandler.fail("INVALID_NUMBER", f"'{name}' must be an integer.", f"Set '{name}' to a whole number.")

    @classmethod
    def run(cls):
        parser=cls.build_parser(); output=Output(False)
        try:
            args=parser.parse_args(); output=Output(args.human)
            if args.prompt or args.command=="prompt": print(cls.PROMPT); return 0
            if args.json_input: return cls.json_input(output)
            if not args.command:
                print(cls.PROMPT)
                return 0
            path=Path(args.file); FileSystemManager.cleanup_transactions(path); editor=FileEditor(path,output)
            if args.command=="rewrite":
                editor.rewrite(cls.read_stdin_if_available())
            elif args.command=="create":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_INPUT","Create content must be supplied on stdin.")
                editor.create(v)
            elif args.command=="read": editor.read(args.hash,args.before,args.after)
            elif args.command=="search":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_QUERY","Search text must be supplied on stdin.")
                editor.search(v,args.regex,args.limit,args.before,args.after)
            elif args.command=="replace":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_INPUT","Replacement content must be supplied on stdin.")
                a,b=cls.split_target(args.target); editor.mutate("replace",a,b,v)
            elif args.command=="insert":
                v=cls.read_stdin_if_available()
                if v is None: ErrorHandler.fail("MISSING_INPUT","Insertion content must be supplied on stdin.")
                editor.mutate("insert",args.hash,None,v,args.position)
            elif args.command=="delete":
                a,b=cls.split_target(args.target); editor.mutate("delete",a,b,None)
            return 0
        except ToolError as exc:
            output.error(exc); return 1
        except KeyboardInterrupt:
            output.error(ToolError("CANCELLED","Operation cancelled.")); return 130

if __name__ == "__main__":
    sys.exit(CLI.run())