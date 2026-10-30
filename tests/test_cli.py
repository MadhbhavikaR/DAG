"""Regression tests for the public CLI and filesystem safety invariants."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from edit.editor import FileEditor
from edit.errors import ToolError
from edit.hashing import HashEngine
from edit.output import Output
from edit.text_utils import TextUtils

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "edit.py"


def run_cli(
    *args: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        input=input_text,
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )


def create_file(path: Path, content: str) -> dict:
    result = run_cli("create", str(path), input_text=content)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def search_hash(path: Path, query: str) -> str:
    result = run_cli("search", str(path), input_text=query)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["count"] >= 1
    return payload["matches"][0]["hash"]


def test_prompt_is_available_without_a_file() -> None:
    result = run_cli("--prompt")
    assert result.returncode == 0
    assert "SEARCH" in result.stdout
    assert result.stderr == ""


def test_create_search_and_read_use_json_contract(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    payload = create_file(target, "alpha\nbeta\n")
    assert payload == {"ok": True, "operation": "create", "lines": 2}

    anchor = search_hash(target, "beta")
    result = run_cli("read", str(target), anchor)
    read_payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert read_payload["operation"] == "read"
    assert any(row["text"] == "beta" for row in read_payload["context"])


def test_replace_uses_fresh_anchor_and_reports_new_context(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    create_file(target, "alpha\nbeta\n")
    anchor = search_hash(target, "beta")

    result = run_cli("replace", str(target), anchor, input_text="gamma\n")
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["ok"] is True
    assert payload["operation"] == "replace"
    assert target.read_text(encoding="utf-8") == "alpha\ngamma\n"
    assert payload["anchor"]


def test_stale_anchor_fails_as_json_on_stderr(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    create_file(target, "alpha\nbeta\n")

    result = run_cli("replace", str(target), "deadbeef", input_text="gamma\n")
    payload = json.loads(result.stderr)
    assert result.returncode == 1
    assert payload["ok"] is False
    assert payload["error"] == "STALE_HASH"


def test_create_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("keep\n", encoding="utf-8")

    result = run_cli("create", str(target), input_text="overwrite\n")
    payload = json.loads(result.stderr)
    assert result.returncode == 1
    assert payload["error"] == "FILE_EXISTS"
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_mutation_preserves_crlf_newlines(tmp_path: Path) -> None:
    target = tmp_path / "windows.txt"
    target.write_bytes(b"alpha\r\nbeta\r\n")
    anchor = search_hash(target, "beta")

    result = run_cli("replace", str(target), anchor, input_text="gamma\n")
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == b"alpha\r\ngamma\r\n"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits are required")
def test_mutation_preserves_existing_file_mode(tmp_path: Path) -> None:
    target = tmp_path / "mode.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    target.chmod(0o640)
    anchor = search_hash(target, "beta")

    result = run_cli("replace", str(target), anchor, input_text="gamma\n")
    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_delete_can_remove_all_lines(tmp_path: Path) -> None:
    target = tmp_path / "single.txt"
    create_file(target, "only line\n")
    anchor = search_hash(target, "only line")

    result = run_cli("delete", str(target), anchor)
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["operation"] == "delete"
    assert payload["lines_after"] == 0
    assert target.read_bytes() == b""


def test_invalid_regex_is_a_structured_error(tmp_path: Path) -> None:
    target = tmp_path / "regex.txt"
    create_file(target, "some text\n")

    result = run_cli("search", str(target), input_text="[")
    # Literal search is the default; malformed regex syntax is only rejected
    # when regex mode is explicitly requested.
    assert result.returncode == 0
    assert json.loads(result.stdout)["count"] == 0

    result = run_cli("search", str(target), "--regex", input_text="[")
    payload = json.loads(result.stderr)
    assert result.returncode == 1
    assert payload["error"] == "INVALID_REGEX"


def test_concurrent_change_after_anchor_resolution_aborts_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "concurrent-after-anchor.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    editor = FileEditor(target, Output(False))
    original_load = editor._load
    snapshot = original_load()
    anchor = snapshot[4]["sequence"][1]

    def load_then_external_change():
        loaded = original_load()
        target.write_text("external change\n", encoding="utf-8")
        return loaded

    monkeypatch.setattr(editor, "_load", load_then_external_change)
    with pytest.raises(ToolError) as caught:
        editor.mutate("replace", anchor, None, "gamma\n")

    assert caught.value.code == "STALE_FILE"
    assert target.read_text(encoding="utf-8") == "external change\n"



@pytest.mark.parametrize(
    ("content", "newline", "expected"),
    [
        ("alpha", "\n", "alpha\n"),
        ("alpha\n", "\n", "alpha\n"),
        ("alpha\r\nbeta\r\n", "\r\n", "alpha\r\nbeta\r\n"),
        ("alpha\rbeta\r", "\r", "alpha\rbeta\r"),
        ("alpha\nbeta\r\ngamma\r", "\n", "alpha\nbeta\ngamma\n"),
        ("", "\n", ""),
    ],
)
def test_content_normalization_is_idempotent_and_uses_selected_newline(
    content: str, newline: str, expected: str
) -> None:
    normalized = TextUtils.normalize_content(content, newline)
    assert normalized == expected
    assert TextUtils.normalize_content(normalized, newline) == normalized


def test_ambiguous_hash_is_rejected() -> None:
    index = {
        "lines": {
            "deadbeef": [
                {"index": 0, "offset": 0, "length": 5},
                {"index": 2, "offset": 10, "length": 5},
            ]
        }
    }

    with pytest.raises(ToolError) as caught:
        HashEngine.resolve_unique(index, "deadbeef", Path("sample.txt"))

    assert caught.value.code == "AMBIGUOUS_HASH"


def test_hash_collision_during_mutation_does_not_write_file(
    tmp_path: Path, monkeypatch
) -> None:
    target = tmp_path / "collision.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")
    editor = FileEditor(target, Output(False))
    anchor = editor._load()[4]["sequence"][1]
    original = target.read_bytes()

    monkeypatch.setattr(HashEngine, "generate_all", lambda lines: ["deadbeef"] * len(lines))

    with pytest.raises(ToolError) as caught:
        editor.mutate("replace", anchor, None, "gamma\n")

    assert caught.value.code == "HASH_COLLISION"
    assert target.read_bytes() == original
