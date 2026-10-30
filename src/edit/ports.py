"""Small structural contracts for application-level dependency inversion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .errors import ToolError


class OutputPort(Protocol):
    def ok(self, data: dict[str, Any]) -> None:
        ...

    def error(self, exc: ToolError) -> None:
        ...


class FileSystemPort(Protocol):
    def read_bytes(self, path: Path) -> bytes:
        ...

    def create_file(self, path: Path, content: bytes) -> None:
        ...

    def read_file(self, path: Path) -> tuple[list[str], str, str, bytes]:
        ...

    def atomic_replace(self, path: Path, new_text: str) -> None:
        ...

    def cleanup_transactions(self, path: Path) -> None:
        ...


class HashPort(Protocol):
    def generate_all(self, lines: list[str]) -> list[str]:
        ...

    def validate(self, value: str) -> str:
        ...

    def resolve_unique(self, index: dict[str, Any], value: str, path: Path) -> int:
        ...

    def enforce_uniqueness(self, hashes: list[str]) -> None:
        ...


class IndexPort(Protocol):
    def get_current_index(
        self, path: Path, raw: bytes, lines: list[str], newline: str
    ) -> dict[str, Any]:
        ...


class MutationPort(Protocol):
    def execute(
        self, lines: list[str], start: int, end: int, content: str | None, newline: str
    ) -> tuple[list[str], int, str]:
        ...


class MutationProvider(Protocol):
    def get(self, name: str, position: str | None = None) -> MutationPort:
        ...


class TextPort(Protocol):
    def normalize_content(self, content: str, newline: str) -> str:
        ...

    def line_body(self, line: str) -> str:
        ...

    def clip(self, body: str) -> str:
        ...

    def detect_newline(self, text: str) -> str:
        ...
