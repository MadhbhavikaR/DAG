"""Argument parser with structured validation errors."""

import argparse

from .errors import ManagerError

class ManagerArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ManagerError(
            "INVALID_COMMAND",
            f"invalid command arguments: {message}",
            "Run 'manager --prompt' to review the command protocol, then rerun with valid arguments.",
        )
