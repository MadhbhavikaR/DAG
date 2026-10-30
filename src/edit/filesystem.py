from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from .config import Config
from .errors import ErrorHandler, ToolError
from .text_utils import TextUtils


class FileSystemManager:
    @staticmethod
    def read_bytes(path: Path) -> bytes:
        return path.read_bytes()

    @staticmethod
    def create_file(path: Path, content: bytes) -> None:
        try:
            with path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            ErrorHandler.fail("CREATE_FAILED", f"Unable to create '{path}': {exc}")
        FileSystemManager._fsync_directory(path.parent)

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
