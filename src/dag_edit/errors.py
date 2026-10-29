from __future__ import annotations

import argparse
from typing import NoReturn


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
