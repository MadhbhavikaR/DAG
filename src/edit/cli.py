"""Command-line adapters for the Edit application."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .config import Config
from .editor import FileEditor
from .errors import AgentArgumentParser, ErrorHandler, ToolError
from .filesystem import FileSystemManager
from .output import Output
from .ports import FileSystemPort


PROMPT = """edit PROTOCOL (one text file, JSON out; --human for people)
stdin carries content and search text.

CREATE   printf '%s\\n' 'l1' 'l2' | edit create FILE      (fails if FILE exists)
REWRITE  printf '%s\\n' 'l1' 'l2' | edit rewrite FILE     (replaces all of FILE)
SEARCH   printf '%s' 'text' | edit search FILE      (literal; --regex opt-in; max 5 hits)
READ     edit read FILE HASH [BEFORE AFTER]
REPLACE  printf '%s\\n' 'new' | edit replace FILE HASH
         printf '%s\\n' 'a' 'b' | edit replace FILE START..END
INSERT   printf '%s\\n' 'new' | edit insert before|after FILE HASH
DELETE   edit delete FILE HASH        edit delete FILE START..END

HASH comes only from search/read output. START..END is inclusive. Never invent a hash.
SEARCH returns just the matched lines; use READ for surrounding context.
Long lines are clipped with an ellipsis.

WORKFLOW  search -> read if needed -> edit -> use the returned hashes.

JSON INPUT  edit --json-input
{"command":"replace","file":"app.py","target":"HASH..HASH","input":"new text\\n"}
commands: create, rewrite, read, search, replace, insert, delete

ERRORS
STALE_HASH / STALE_FILE  -> search or read again
AMBIGUOUS_HASH           -> pick another observed hash
HASH_COLLISION           -> change the new content
MISSING_INPUT            -> provide stdin input
"""


class StandardInput:
    """Read content from stdin without coupling command dispatch to streams."""

    def read(self) -> str | None:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        try:
            return sys.stdin.read()
        except OSError as exc:
            ErrorHandler.fail("STDIN_FAILED", f"Unable to read stdin: {exc}")


class TargetParser:
    """Parse single-anchor and inclusive range target expressions."""

    @staticmethod
    def parse(target: str) -> tuple[str, str | None]:
        if not target:
            ErrorHandler.fail("MISSING_TARGET", "A target hash is required.")
        parts = target.split("..")
        if len(parts) > 2 or not all(parts):
            ErrorHandler.fail("INVALID_TARGET", "Target must be HASH or START_HASH..END_HASH.")
        return parts[0], parts[1] if len(parts) == 2 else None


class JsonRequestDispatcher:
    """Validate and dispatch one JSON request object."""

    COMMANDS = {"create", "rewrite", "read", "search", "replace", "insert", "delete"}

    def __init__(
        self,
        input_reader: StandardInput,
        editor_factory: Callable[[Path, Output], FileEditor] = FileEditor,
        filesystem: FileSystemPort | None = None,
    ) -> None:
        self.input_reader = input_reader
        self.editor_factory = editor_factory
        self.filesystem = filesystem or FileSystemManager()

    def dispatch(self, output: Output) -> int:
        raw = self.input_reader.read()
        if raw is None:
            ErrorHandler.fail("MISSING_JSON", "JSON request must be supplied on stdin.")
        try:
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            ErrorHandler.fail("INVALID_JSON", f"Invalid JSON: {exc}")
        if not isinstance(request, dict):
            ErrorHandler.fail("INVALID_JSON", "JSON request must be an object.")

        command = request.get("command")
        if command not in self.COMMANDS:
            ErrorHandler.fail(
                "INVALID_COMMAND",
                "command must be create, rewrite, read, search, replace, insert, or delete.",
            )
        filename = request.get("file")
        if not isinstance(filename, str) or not filename:
            ErrorHandler.fail("MISSING_FILE", "file is required.")

        path = Path(filename)
        self.filesystem.cleanup_transactions(path)
        editor = self.editor_factory(path, output)
        value = request.get("input")
        if value is not None and not isinstance(value, str):
            ErrorHandler.fail("INVALID_INPUT", "input must be a string.")

        if command == "rewrite":
            editor.rewrite(value)
        elif command == "create":
            if value is None:
                ErrorHandler.fail("MISSING_INPUT", "Create content must be in input.")
            editor.create(value)
        elif command == "read":
            editor.read(
                request.get("hash"),
                CLI.json_int(request, "before"),
                CLI.json_int(request, "after"),
            )
        elif command == "search":
            editor.search(
                value or "",
                bool(request.get("regex", False)),
                CLI.json_int(request, "limit", 5),
                CLI.json_int(request, "before", Config.DEFAULT_PREVIOUS),
                CLI.json_int(request, "after", Config.DEFAULT_NEXT),
            )
        elif command == "replace":
            start, end = TargetParser.parse(str(request.get("target", "")))
            if value is None:
                ErrorHandler.fail("MISSING_INPUT", "Replacement content must be in input.")
            editor.mutate("replace", start, end, value)
        elif command == "insert":
            if value is None:
                ErrorHandler.fail("MISSING_INPUT", "Insertion content must be in input.")
            editor.mutate(
                "insert", str(request.get("hash", "")), None, value,
                str(request.get("position", "")),
            )
        else:
            start, end = TargetParser.parse(str(request.get("target", "")))
            editor.mutate("delete", start, end, None)
        return 0


class CommandDispatcher:
    """Translate parsed CLI arguments into application service calls."""

    def __init__(
        self,
        input_reader: StandardInput,
        editor_factory: Callable[[Path, Output], FileEditor] = FileEditor,
        filesystem: FileSystemPort | None = None,
    ) -> None:
        self.input_reader = input_reader
        self.editor_factory = editor_factory
        self.filesystem = filesystem or FileSystemManager()

    def dispatch(self, args: argparse.Namespace, output: Output) -> int:
        path = Path(args.file)
        self.filesystem.cleanup_transactions(path)
        editor = self.editor_factory(path, output)

        if args.command == "rewrite":
            editor.rewrite(self.input_reader.read())
        elif args.command == "create":
            content = self.input_reader.read()
            if content is None:
                ErrorHandler.fail("MISSING_INPUT", "Create content must be supplied on stdin.")
            editor.create(content)
        elif args.command == "read":
            editor.read(args.hash, args.before, args.after)
        elif args.command == "search":
            query = self.input_reader.read()
            if query is None:
                ErrorHandler.fail("MISSING_QUERY", "Search text must be supplied on stdin.")
            editor.search(query, args.regex, args.limit, args.before, args.after)
        elif args.command == "replace":
            content = self.input_reader.read()
            if content is None:
                ErrorHandler.fail("MISSING_INPUT", "Replacement content must be supplied on stdin.")
            start, end = TargetParser.parse(args.target)
            editor.mutate("replace", start, end, content)
        elif args.command == "insert":
            content = self.input_reader.read()
            if content is None:
                ErrorHandler.fail("MISSING_INPUT", "Insertion content must be supplied on stdin.")
            editor.mutate("insert", args.hash, None, content, args.position)
        elif args.command == "delete":
            start, end = TargetParser.parse(args.target)
            editor.mutate("delete", start, end, None)
        return 0


class CLI:
    """Compatibility facade and application composition root."""

    PROMPT = PROMPT

    @staticmethod
    def read_stdin_if_available() -> str | None:
        return StandardInput().read()

    @staticmethod
    def split_target(target: str) -> tuple[str, str | None]:
        return TargetParser.parse(target)

    @staticmethod
    def build_parser() -> argparse.ArgumentParser:
        parser = AgentArgumentParser(
            prog="edit",
            description="Single-file create/search/read/replace/insert/delete tool for LLM/SLM agents.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.add_argument("--human", action="store_true", help="Human-readable output. JSON is default.")
        parser.add_argument("--prompt", action="store_true", help="Print the compact agent protocol.")
        parser.add_argument("--json-input", action="store_true", help="Read one JSON request object from stdin.")
        subparsers = parser.add_subparsers(dest="command")

        create = subparsers.add_parser("create", help="Create FILE from stdin.")
        create.add_argument("file")

        rewrite = subparsers.add_parser("rewrite", help="Replace all of FILE from stdin.")
        rewrite.add_argument("file")

        read = subparsers.add_parser("read", help="Read bounded file/context.")
        read.add_argument("file")
        read.add_argument("hash", nargs="?")
        read.add_argument("before", nargs="?", type=int, default=None)
        read.add_argument("after", nargs="?", type=int, default=None)

        search = subparsers.add_parser("search", help="Search stdin text in FILE.")
        search.add_argument("file")
        search.add_argument("--regex", action="store_true")
        search.add_argument("--limit", type=int, default=5)
        search.add_argument("--before", type=int, default=Config.DEFAULT_PREVIOUS)
        search.add_argument("--after", type=int, default=Config.DEFAULT_NEXT)

        replace = subparsers.add_parser("replace", help="Replace HASH or HASH..HASH using stdin.")
        replace.add_argument("file")
        replace.add_argument("target")

        insert = subparsers.add_parser("insert", help="Insert stdin content before or after HASH.")
        insert.add_argument("position", choices=("before", "after"))
        insert.add_argument("file")
        insert.add_argument("hash")

        delete = subparsers.add_parser("delete", help="Delete HASH or HASH..HASH.")
        delete.add_argument("file")
        delete.add_argument("target")

        subparsers.add_parser("prompt", help="Print the compact agent protocol.")
        return parser

    @staticmethod
    def json_int(
        request: dict[str, Any], name: str, default: int | None = None
    ) -> int | None:
        value = request.get(name, default)
        if value is None:
            return None
        if isinstance(value, bool):
            ErrorHandler.fail(
                "INVALID_NUMBER", f"'{name}' must be an integer.",
                f"Set '{name}' to a whole number.",
            )
        try:
            return int(value)
        except (TypeError, ValueError):
            ErrorHandler.fail(
                "INVALID_NUMBER", f"'{name}' must be an integer.",
                f"Set '{name}' to a whole number.",
            )

    @classmethod
    def json_input(cls, output: Output) -> int:
        return JsonRequestDispatcher(StandardInput()).dispatch(output)

    @classmethod
    def run(cls, argv: Sequence[str] | None = None) -> int:
        output = Output(False)
        try:
            args = cls.build_parser().parse_args(argv)
            output = Output(args.human)
            if args.prompt or args.command == "prompt":
                print(cls.PROMPT)
                return 0
            if args.json_input:
                return cls.json_input(output)
            if not args.command:
                print(cls.PROMPT)
                return 0
            return CommandDispatcher(StandardInput()).dispatch(args, output)
        except ToolError as exc:
            output.error(exc)
            return 1
        except KeyboardInterrupt:
            output.error(ToolError("CANCELLED", "Operation cancelled."))
            return 130


def main() -> int:
    """Run the Edit command-line application."""
    return CLI.run()
