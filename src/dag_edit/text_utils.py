from __future__ import annotations

from .config import Config




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
