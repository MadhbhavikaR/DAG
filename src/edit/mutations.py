from __future__ import annotations

from abc import ABC, abstractmethod
from .errors import ErrorHandler
from .text_utils import TextUtils


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
