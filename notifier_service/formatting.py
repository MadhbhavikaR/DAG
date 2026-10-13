"""Formatting helpers for common webhook message conventions."""

from __future__ import annotations

import html
import re
from typing import Literal

MessageFormat = Literal["text", "html", "markdown", "simplified"]


def format_message(message: str, format_name: str) -> str:
    """Format a plain message for a provider's declared content format."""
    match format_name.casefold():
        case "text":
            return re.sub(r"[*_~\x60]", "", message)
        case "html":
            escaped = html.escape(message)
            escaped = re.sub(r"\*(.+?)\*", r"<b>\1</b>", escaped)
            return escaped.replace("\n", "<br>\n")
        case "markdown" | "simplified":
            return message
        case _:
            raise ValueError(
                f"Unsupported message format {format_name!r}; "
                "expected text, html, markdown, or simplified"
            )
