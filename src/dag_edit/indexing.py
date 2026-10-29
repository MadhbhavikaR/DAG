from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import tempfile
from pathlib import Path
from .config import Config
from .errors import ErrorHandler
from .hashing import HashEngine
from .text_utils import TextUtils


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
