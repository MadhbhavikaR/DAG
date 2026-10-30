"""Composable mutation command objects."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .errors import ErrorHandler
from .text_utils import TextUtils


class MutationCommand(ABC):
    """Strategy contract for one file mutation."""

    @abstractmethod
    def execute(
        self,
        lines: list[str],
        start: int,
        end: int,
        content: str | None,
        newline: str,
    ) -> tuple[list[str], int, str]:
        """Return the new lines, context target, and operation name."""
        raise NotImplementedError


class ReplaceCommand(MutationCommand):
    def execute(self, lines, start, end, content, newline):
        if content is None:
            ErrorHandler.fail(
                "MISSING_CONTENT",
                "No replacement content was supplied.",
                "Pipe the replacement block to stdin.",
            )
        replacement = TextUtils.normalize_content(content, newline).splitlines(keepends=True)
        new_lines = lines[:start] + replacement + lines[end + 1:]
        target = start if replacement else min(start, len(new_lines) - 1)
        return new_lines, target, "replace"


class InsertCommand(MutationCommand):
    def __init__(self, position: str) -> None:
        if position not in {"before", "after"}:
            ErrorHandler.fail("INVALID_POSITION", "INSERT position must be 'before' or 'after'.")
        self.position = position

    def execute(self, lines, start, end, content, newline):
        if content is None:
            ErrorHandler.fail(
                "MISSING_CONTENT",
                "No insertion content was supplied.",
                "Pipe the insertion block to stdin.",
            )
        inserted = TextUtils.normalize_content(content, newline).splitlines(keepends=True)
        if not inserted:
            ErrorHandler.fail(
                "EMPTY_CONTENT",
                "Insertion content is empty.",
                "Pipe at least one line to stdin.",
            )
        if self.position == "before":
            return lines[:start] + inserted + lines[start:], start + len(inserted), "insert"
        return lines[:end + 1] + inserted + lines[end + 1:], end + len(inserted), "insert"


class DeleteCommand(MutationCommand):
    def execute(self, lines, start, end, content, newline):
        new_lines = lines[:start] + lines[end + 1:]
        target = min(start, len(new_lines) - 1) if new_lines else -1
        return new_lines, target, "delete"


class MutationRegistry:
    """Resolve mutation names to interchangeable command strategies."""

    def __init__(self) -> None:
        self._commands = {
            "replace": lambda position: ReplaceCommand(),
            "delete": lambda position: DeleteCommand(),
            "insert": lambda position: InsertCommand(position or ""),
        }

    def register(self, name: str, factory) -> None:
        """Register an additional command without modifying editor orchestration."""
        if not name or name in self._commands:
            raise ValueError(f"Mutation command '{name}' is already registered or invalid.")
        self._commands[name] = factory

    def get(self, name: str, position: str | None = None) -> MutationCommand:
        factory = self._commands.get(name)
        if factory is None:
            ErrorHandler.fail("UNSUPPORTED_COMMAND", f"Unsupported command '{name}'.")
        return factory(position)


class MutationFactory:
    """Backward-compatible facade for callers using the previous factory API."""

    @staticmethod
    def get(name: str, position: str | None = None) -> MutationCommand:
        return MutationRegistry().get(name, position)
