from __future__ import annotations

import argparse
import io
import json
import os
import re
import signal
import shlex
import subprocess
import shutil
import sys
from pathlib import Path
from typing import Any

from .core import (
    FORMAT_VERSION, PHASE_ROLE, STEP_STATES, STORY_ACTIVE_STATES, TASK_STATES, TASK_TRANSITIONS, ManagerError,
    Store, Task, Step, atomic_write, generated_agent_id, now, fail, parse_task_id, protect, rel_safe,
)

PROMPT = """MANAGER PROTOCOL (LOW-CONTEXT SAFE)
The manager owns workflow state. Never edit .manager directly.
All commands return JSON by default.

LLM IDENTITY
- You are an LLM agent operating under Manager control.
- Keep responses short, explicit, and deterministic.
- Read AGENT_ID from manager next.
- Reuse that AGENT_ID for every task interaction.
- Include agent_id in every stdin JSON payload for submit, finding, decision, evidence, and plan submit commands.

ASD-STE100 STYLE REQUIREMENT
- Use Simplified Technical English (ASD-STE100 style) for natural-language output.
- Use short sentences.
- Use one instruction per sentence.
- Use active voice.
- Avoid ambiguous words.
- Use the same term for the same concept.
- Prefer command form for required actions.

START LOOP
1) manager next
2) If NEXT_COMMAND == "manager context", run:
   manager context --compact --max-chars 1200
3) manager submit-schema
4) Prepare one JSON payload that matches RETURN_SCHEMA exactly.
5) manager submit < payload.json
6) If ERROR appears, execute DO exactly and retry.
7) Repeat until NO_TASK.

NON-NEGOTIABLE
- Perform only ACTION and stay within BOUNDARY.
- Never invent IDs, roles, states, evidence, or commit hashes.
- Never commit manually; manager owns commit transitions.

DISCOVERY
- For nested subcommands use: manager task --help, manager decision --help, manager learn --help, manager plan --help.
- Commands that read stdin require piped/heredoc input (task add/edit, finding add, evidence add, decision propose/resolve, learn add, submit, plan submit, block).
- If current external information is required, use available research tools (for example web search) and cite evidence before deciding.
"""


class ManagerArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ManagerError(
            "INVALID_COMMAND",
            f"invalid command arguments: {message}",
            "Run 'manager --prompt' to review the command protocol, then rerun with valid arguments.",
        )


def stdin_json() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ManagerError("INVALID_JSON", f"invalid JSON: {exc.msg}", "Submit one JSON object matching RETURN_SCHEMA from 'manager next'.")
    if not isinstance(value, dict):
        raise ManagerError("INVALID_JSON", "stdin must contain one JSON object", "Submit one JSON object matching RETURN_SCHEMA from 'manager next'.")
    return value


def ensure_keys(value: dict[str, Any], allowed: set[str], required: set[str] = set()) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ManagerError("INVALID_SCHEMA", "unsupported field(s): " + ", ".join(unknown), "Remove unsupported fields and resubmit exactly the schema returned by 'manager next'.")
    missing = sorted(required - set(value))
    if missing:
        raise ManagerError("INVALID_SCHEMA", "missing required field(s): " + ", ".join(missing), "Add the required field(s): " + ", ".join(missing) + ".")


def require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManagerError("INVALID_SCHEMA", f"{field} must be a non-empty string", f"Provide a non-empty {field} and resubmit.")
    return value.strip()


def require_list(value: Any, field: str, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ManagerError("INVALID_SCHEMA", f"{field} must be a {'non-empty ' if nonempty else ''}array", f"Provide {field} as an array and resubmit.")
    return value


def require_string_list(value: Any, field: str, nonempty: bool = False) -> list[str]:
    values = require_list(value, field, nonempty)
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ManagerError("INVALID_SCHEMA", f"{field} must contain only non-empty strings", f"Provide {field} as an array of non-empty strings.")
    return [item.strip() for item in values]


def active_task_agent_id(task: Task) -> str:
    agent_id = task.agent_id.strip()
    if not agent_id:
        raise ManagerError(
            "CORRUPT_STATE",
            f"task {task.id} has no agent_id",
            "Repair managed task agent_id values so each task stores a UUIDv4.",
        )
    return agent_id


def require_payload_agent_id(payload: dict[str, Any], task: Task) -> str:
    submitted_agent_id = require_str(payload.get("agent_id"), "agent_id")
    expected_agent_id = active_task_agent_id(task)
    if submitted_agent_id != expected_agent_id:
        raise ManagerError(
            "AGENT_ID_MISMATCH",
            f"agent_id '{submitted_agent_id}' does not match active task agent_id '{expected_agent_id}'",
            "Use the AGENT_ID from 'manager next' for the current task and resubmit.",
        )
    return submitted_agent_id


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)

MAX_SUBMITTED_TEXT = 8000
DEFAULT_CONTEXT_MAX_CHARS = 1200
MAX_ERROR_LOG_TEXT = 16000
STDIN_READ_TIMEOUT_SECONDS = max(1, int(os.getenv("MANAGER_STDIN_TIMEOUT_SECONDS", "120")))
RUNTIME_DIR = "runtime"
RETURN_SCHEMA_FILE = "return-schema.json"
TASK_ADD_SCHEMA_FILE = "task-add-input.schema.json"
ERROR_LOG_FILE = "error-log.ndjson"
ERROR_LOG_FILE_TEMPLATE = "error-{agent_id}-log.ndjson"
LAST_COMMAND_LOG_FILE_TEMPLATE = "last-10-{agent_id}-log.ndjson"
LAST_COMMAND_QUEUE_CAPACITY = 10
ASD_STE100_REMINDER = "ASD-STE100 reminder: use short, clear, active sentences."
RESEARCH_REMINDER = "When current external information is required, use available research tools (for example web search) and cite the source evidence."
MICRO_CYCLE = [
    "Run manager next.",
    "If next_command is manager context, load only listed LOAD IDs using compact context.",
    "Run manager submit-schema and submit exactly that schema.",
    "On error, execute DO exactly; do not improvise fixes outside manager instructions.",
    "Use research tools when current external information is required; do not assume unknown facts.",
]
ERROR_HINTS: dict[str, str] = {
    "INVALID_SCHEMA": "Resubmit using the exact active RETURN_SCHEMA.",
    "INCOMPLETE_VALIDATION": "Each required validation command must appear exactly once.",
    "UNREACHABLE_CONTEXT": "Load only IDs listed in LOAD from the current envelope.",
    "TOKEN_REUSE": "Submission tokens are idempotency keys and cannot be reused with different payloads.",
    "NO_TASK": "Create/select work before retrying workflow commands that require an active task.",
    "NO_COMMAND": "Start by loading the protocol prompt and then follow manager next.",
    "AGENT_ID_MISMATCH": "Use the AGENT_ID from the current manager next envelope.",
}

ERROR_GOTCHAS: dict[str, str] = {
    "INVALID_SCHEMA": "Do not add unsupported fields or omit required fields.",
    "INVALID_JSON": "Do not submit plain text or arrays; submit exactly one JSON object.",
    "INCOMPLETE_VALIDATION": "Do not skip commands listed in VALIDATION.",
    "UNAUTHORIZED_VALIDATION": "Do not run commands outside the accepted plan.",
    "UNREACHABLE_CONTEXT": "Do not invent FINDING/DEC/EVT IDs.",
    "TOKEN_REUSE": "Do not reuse a token after modifying the payload.",
    "NO_TASK": "Do not loop manager next after NO_TASK without creating/selecting work.",
    "INPUT_TIMEOUT": "Do not run stdin-driven commands interactively without piping payload data.",
    "INTERNAL_ERROR": "Do not mutate manager state manually to work around unexplained internal failures.",
    "AGENT_ID_MISMATCH": "Do not reuse an AGENT_ID from another task or story.",
}

ERROR_RECOVERY_COMMANDS: dict[str, list[str]] = {
    "NO_TASK": ["manager status --compact", "manager task add", "manager next"],
    "INVALID_JSON": ["manager submit-schema --schema-path", "manager submit"],
    "INVALID_SCHEMA": ["manager submit-schema --schema-path", "manager submit"],
    "INCOMPLETE_VALIDATION": ["manager next", "manager submit-schema --schema-path", "manager submit"],
    "UNAUTHORIZED_VALIDATION": ["manager next", "manager submit-schema --schema-path", "manager submit"],
    "INVALID_PHASE": ["manager next", "manager submit-schema --schema-path", "manager submit"],
    "INPUT_TIMEOUT": ["manager submit-schema --schema-path", "manager submit"],
}


def read_stdin_with_timeout(stream: Any, timeout_seconds: int, command: str) -> str:
    def _timeout_handler(signum: int, frame: Any) -> None:
        _ = signum
        _ = frame
        raise TimeoutError("stdin read timed out")

    previous = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout_seconds)
    try:
        return stream.read()
    except TimeoutError as exc:
        raise ManagerError(
            "INPUT_TIMEOUT",
            f"{command} requires stdin input but no payload was received within {timeout_seconds} seconds",
            f"Provide stdin input via file/pipe/heredoc and rerun '{command}'.",
        ) from exc
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def error_hint(code: str) -> str | None:
    return ERROR_HINTS.get(code)


def error_gotcha(code: str) -> str:
    return ERROR_GOTCHAS.get(code, "Do not edit .manager directly or bypass manager-owned transitions.")


def state_available_commands(store: Store) -> list[str]:
    try:
        with store.lock():
            store.initialize()
            tasks = store.load_tasks()
            task = selected_task(store, tasks)
            if not task:
                return ["manager status --compact", "manager task add", "manager next"]
            if task.status == "blocked":
                return [f"manager unblock {task.id}", "manager status --compact", "manager next"]
            if task.status != "active" or not task.phase:
                return ["manager next", "manager status --compact"]
            phase_map = {
                "analysis": ["manager context --compact --max-chars 1200", "manager submit-schema --schema-path", "manager submit"],
                "planning": ["manager context --compact --max-chars 1200", "manager submit-schema --schema-path", "manager submit"],
                "implementation": ["manager submit-schema --schema-path", "manager submit", "manager next"],
                "step_validation": ["manager submit-schema --schema-path", "manager submit", "manager next"],
                "step_commit": ["manager submit-schema --schema-path", "manager submit", "manager next"],
                "final_validation": ["manager submit-schema --schema-path", "manager submit", "manager next"],
                "final_commit": ["manager submit-schema --schema-path", "manager submit", "manager next"],
            }
            return phase_map.get(task.phase, ["manager next", "manager status --compact"])
    except (ManagerError, OSError, ValueError):
        return ["manager status --compact", "manager next"]


def state_reference_hint(store: Store, schema_path: str | None = None) -> str:
    commands = state_available_commands(store)
    cmd_text = " ; ".join(commands)
    if schema_path:
        return f"Available commands in current state: {cmd_text}. Schema reference: {schema_path}."
    return f"Available commands in current state: {cmd_text}."


def gotcha_reference(exc: ManagerError) -> str:
    return error_gotcha(exc.code)


def compose_error_payload(exc: ManagerError, store: Store, schema_path: str | None = None) -> dict[str, Any]:
    do_text = recovery_do_for_error(exc, schema_path=schema_path) or exc.do
    hint_base = error_hint(exc.code)
    hint_state = state_reference_hint(store, schema_path=schema_path)
    hint = ((hint_base + " " if hint_base else "") + hint_state + f" {ASD_STE100_REMINDER}").strip()
    payload: dict[str, Any] = {
        "error": exc.code,
        "what": exc.what,
        "do": do_text,
        "hint": hint.strip(),
        "gotcha": gotcha_reference(exc),
    }
    if schema_path:
        payload["schema_path"] = schema_path
    return payload


def render_manager_error(exc: ManagerError, store: Store, as_json: bool = False, schema_path: str | None = None) -> str:
    payload = compose_error_payload(exc, store, schema_path=schema_path)
    if as_json:
        return json.dumps(payload, indent=2)
    message = f"ERROR: {payload['error']}\nWHAT: {payload['what']}\nDO: {payload['do']}\nHINT: {payload['hint']}\nGOTCHA: {payload['gotcha']}"
    if schema_path:
        message += f"\nSCHEMA_PATH: {schema_path}"
    return message


def recovery_do_for_error(exc: ManagerError, schema_path: str | None = None) -> str | None:
    commands = ERROR_RECOVERY_COMMANDS.get(exc.code)
    if exc.code == "INVALID_SCHEMA" and schema_path and Path(schema_path).name == TASK_ADD_SCHEMA_FILE:
        commands = ["manager task add", "manager next"]
    if not commands:
        return None
    rendered: list[str] = []
    for command in commands:
        if command == "manager task add" and schema_path:
            rendered.append(f"cat <<'JSON' | manager task add  # payload must match {schema_path}")
        elif command == "manager submit" and schema_path:
            rendered.append(f"manager submit < payload.json  # payload must match {schema_path}")
        else:
            rendered.append(command)
    return "Run these commands in order: " + " ; ".join(rendered)


def emit_output(value: Any, as_json: bool = False) -> str:
    if as_json:
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return json.dumps({"result": value}, indent=2)
            return json.dumps(parsed, indent=2)
        return json.dumps({"result": value}, indent=2)
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2)


def runtime_path(store: Store, name: str) -> Path:
    return store.meta / RUNTIME_DIR / name


def sanitize_agent_id(agent_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (agent_id or "").strip()).strip("-._")
    return cleaned or generated_agent_id("runtime")


def error_log_file_name(agent_id: str) -> str:
    return ERROR_LOG_FILE_TEMPLATE.format(agent_id=sanitize_agent_id(agent_id))


def last_command_log_file_name(agent_id: str) -> str:
    return LAST_COMMAND_LOG_FILE_TEMPLATE.format(agent_id=sanitize_agent_id(agent_id))


def truncate_for_log(value: str, limit: int = MAX_ERROR_LOG_TEXT) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def persist_return_schema(store: Store, schema: dict[str, Any]) -> str:
    path = runtime_path(store, RETURN_SCHEMA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(schema, indent=2) + "\n")
    protect(path)
    return path.relative_to(store.root).as_posix()


def task_add_input_schema() -> dict[str, Any]:
    task_item_schema = {
        "title": "string, required",
        "what": "string, optional but required before planning",
        "done_when": "string, optional but required before planning",
        "why": "string, optional",
        "how": "string, optional",
        "constraints": ["string"],
        "priority": "integer 0..99, optional (default 3)",
    }
    return {
        **task_item_schema,
        "parent": "S00001T00001, optional",
        "items": [task_item_schema],
    }


def persist_task_add_schema(store: Store) -> str:
    path = runtime_path(store, TASK_ADD_SCHEMA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(task_add_input_schema(), indent=2) + "\n")
    protect(path)
    return path.relative_to(store.root).as_posix()


def resolve_task_add_schema_path(store: Store) -> str | None:
    try:
        with store.lock():
            store.initialize()
            return persist_task_add_schema(store)
    except (ManagerError, OSError, ValueError):
        return None


def no_task_payload(store: Store) -> dict[str, Any]:
    try:
        schema_path = persist_task_add_schema(store)
    except (ManagerError, OSError, ValueError):
        schema_path = None
    return {
        "result": "NO_TASK",
        "what": "no active or planned task is currently available",
        "do": "Run 'manager status --compact'. If task is NO_TASK, run 'manager task add' with a payload matching schema_path, then run 'manager next'.",
        "hint": f"Use the schema_path file to create a valid task-add payload before retrying manager next. {RESEARCH_REMINDER} {ASD_STE100_REMINDER}",
        "next_commands": [
            "manager status --compact",
            "manager task add",
            "manager next",
        ],
        "schema_path": schema_path,
    }


def resolve_active_return_schema_path(store: Store) -> str | None:
    try:
        with store.lock():
            store.initialize()
            tasks = store.load_tasks()
            task = selected_task(store, tasks)
            if not task or task.status != "active":
                return None
            payload = next_envelope_payload(store, task, promote_ready=False)
            if not payload:
                return None
            return persist_return_schema(store, payload["return_schema"])
    except (ManagerError, OSError, ValueError):
        return None

def _parse_rendered_output(rendered_output: str) -> Any:
    try:
        return json.loads(rendered_output)
    except json.JSONDecodeError:
        return truncate_for_log(rendered_output)


def _read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    content = "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records)
    atomic_write(path, content)
    protect(path)


def task_sequence_for_id(task_id: str) -> int:
    _, root, subs = parse_task_id(task_id)
    return subs[-1] if subs else root


def resolve_agent_id_for_logging(store: Store) -> str:
    try:
        with store.lock():
            store.initialize()
            tasks = store.load_tasks(validate=False)
            task = selected_task(store, tasks)
            if task and task.agent_id.strip():
                return sanitize_agent_id(task.agent_id)
    except (ManagerError, OSError, ValueError):
        pass
    return sanitize_agent_id(generated_agent_id("no-task"))


def record_command_outcome(
    store: Store,
    argv: list[str],
    stdin_payload: str,
    rendered_output: str,
    success: bool,
    command_name: str | None = None,
) -> None:
    try:
        if success and command_name == "verify" and not store.meta.exists():
            return
        store.meta.mkdir(parents=True, exist_ok=True)
        agent_id = resolve_agent_id_for_logging(store)
        queue_path = runtime_path(store, last_command_log_file_name(agent_id))
        error_path = runtime_path(store, error_log_file_name(agent_id))
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.parent.mkdir(parents=True, exist_ok=True)
        output = _parse_rendered_output(rendered_output)
        status = "success" if success else "failure"
        entry = {
            "recorded_at": now(),
            "command": " ".join(["manager", *argv]).strip(),
            "argv": argv,
            "status": status,
            "agent_id": agent_id,
            "input": truncate_for_log(stdin_payload),
            "output": output,
        }
        queue_records = _read_ndjson(queue_path)
        queue_records.append(entry)
        queue_records = queue_records[-LAST_COMMAND_QUEUE_CAPACITY:]
        if success:
            _write_ndjson(queue_path, queue_records)
            return
        error_records = _read_ndjson(error_path)
        error_records.extend(queue_records)
        _write_ndjson(error_path, error_records)
        _write_ndjson(queue_path, [])
    except (OSError, TypeError, ValueError):
        return


def optional_token(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ManagerError("INVALID_SCHEMA", "submission_token must be a string", "Provide the manager-issued submission token as a string or omit it.")
    return value.strip()

def reject_secret(text: str, field: str) -> None:
    if len(text) > MAX_SUBMITTED_TEXT:
        raise ManagerError("OUTPUT_TOO_LARGE", f"{field} exceeds the {MAX_SUBMITTED_TEXT}-character submission limit", "Submit a concise result containing the exit code, digest, and a bounded head/tail summary.")
    if any(rx.search(text) for rx in SECRET_PATTERNS):
        raise ManagerError("SENSITIVE_OUTPUT", f"{field} appears to contain secret material", "Redact credentials, tokens, private keys, and other secrets before resubmitting.")

def validate_command(command: Any, field: str) -> str:
    value = require_str(command, field)
    reject_secret(value, field)
    try:
        parts = shlex.split(value, posix=True)
    except ValueError as exc:
        raise ManagerError("INVALID_COMMAND", f"{field} is not a valid command expression: {exc}", "Resubmit the exact executable and arguments as a single canonical command string.") from exc
    if not parts or any(ch in value for ch in (";", "&&", "||", "|", ">", "<", "`", "\n", "\r")):
        raise ManagerError("INVALID_COMMAND", f"{field} contains shell control syntax", "Use one executable with explicit arguments; do not submit shell pipelines, redirects, or command chaining.")
    return value


def command_argv(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError as exc:
        raise ManagerError("INVALID_COMMAND", f"stored command is malformed: {exc}", "Repair the accepted plan through an administrative recovery procedure before continuing.") from exc


def repository_relative_path(value: str) -> str | None:
    try:
        return rel_safe(value)
    except ValueError:
        return None


def git_head_commit(store: Store) -> str:
    out = store.git(["rev-parse", "HEAD"], check=False)
    commit_id = out.stdout.strip()
    return commit_id if out.returncode == 0 and commit_id else "unavailable"


def parse_repo_file_reference(value: str) -> tuple[str, int] | None:
    candidate = value.split("|", 1)[0].strip()
    if not candidate:
        return None
    line_number = 1
    base = candidate
    head, sep, tail = candidate.rpartition(":")
    if sep and tail.isdigit() and head:
        base = head
        line_number = max(1, int(tail))
    rel = repository_relative_path(base)
    if rel is None:
        return None
    target = Path(rel)
    if target == Path("."):
        return None
    return rel, line_number


def format_file_evidence_entry(rel_path: str, line_number: int, commit_id: str, state: str = "before") -> str:
    return f"{rel_path}:{line_number} | commit={commit_id} | state={state}"


def enrich_file_evidence_list(
    store: Store,
    items: list[str],
    *,
    state: str = "before",
    commit_id: str | None = None,
) -> list[str]:
    if not store.git_info()[0]:
        return items
    resolved_commit = commit_id or git_head_commit(store)
    enriched: list[str] = []
    for item in items:
        text = item.strip()
        if " | commit=" in text and " | state=" in text:
            enriched.append(item)
            continue
        parsed = parse_repo_file_reference(text)
        if parsed is None:
            enriched.append(item)
            continue
        rel, line_number = parsed
        target = store.root / rel
        if not target.exists():
            enriched.append(item)
            continue
        enriched.append(format_file_evidence_entry(rel, line_number, resolved_commit, state=state))
    return enriched
def truncate_text(value: str, max_chars: int) -> str:
    text = value.strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def extract_section(chunk: str, heading: str) -> str:
    marker = heading + ":"
    pattern = re.compile(r"^" + re.escape(marker) + r"\n(.*?)(?=\n\n[A-Z][A-Z_]*:|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(chunk)
    return match.group(1).strip() if match else ""


def compact_context_record(rid: str, typ: str, chunk: str, max_chars: int) -> str:
    lines = [f"CONTEXT: {rid}", f"TYPE: {typ}", "SUMMARY:"]
    if typ == "finding":
        finding = truncate_text(extract_section(chunk, "FINDING"), max_chars // 2)
        impact = truncate_text(extract_section(chunk, "IMPACT"), max_chars // 4)
        confidence = extract_section(chunk, "CONFIDENCE")
        evidence = extract_section(chunk, "EVIDENCE")
        evidence_items = [x[2:].strip() for x in evidence.splitlines() if x.startswith("- ")][:3]
        if finding:
            lines.append(f"- finding: {finding}")
        if impact:
            lines.append(f"- impact: {impact}")
        if confidence:
            lines.append(f"- confidence: {confidence}")
        if evidence_items:
            lines.append("- evidence: " + "; ".join(truncate_text(x, 80) for x in evidence_items))
    elif typ == "decision":
        status = extract_section(chunk, "STATUS")
        decision = truncate_text(extract_section(chunk, "DECISION"), max_chars // 2)
        rationale = truncate_text(extract_section(chunk, "RATIONALE"), max_chars // 3)
        supersedes = extract_section(chunk, "SUPERSEDES")
        if status:
            lines.append(f"- status: {status}")
        if decision:
            lines.append(f"- decision: {decision}")
        if rationale:
            lines.append(f"- rationale: {rationale}")
        if supersedes and supersedes != "None":
            lines.append(f"- supersedes: {supersedes}")
    else:
        ev_type = extract_section(chunk, "TYPE")
        recorded = extract_section(chunk, "RECORDED_AT")
        if ev_type:
            lines.append(f"- event_type: {ev_type}")
        if recorded:
            lines.append(f"- recorded_at: {recorded}")
        other = []
        for raw in chunk.splitlines():
            if raw.endswith(":") and raw[:-1] not in {"TYPE", "RECORDED_AT"}:
                other.append(raw[:-1].lower())
            if len(other) == 4:
                break
        if other:
            lines.append("- fields: " + ", ".join(other))
    rendered = "\n".join(lines).rstrip() + "\n"
    return truncate_text(rendered, max_chars).rstrip() + "\n"

def selected_task(store: Store, tasks: dict[str, Task]) -> Task | None:
    active = [t for t in tasks.values() if t.status == "active"]
    if active:
        return sorted(active, key=lambda t: t.order_key)[0]
    candidates = [t for t in tasks.values() if t.status in {"planned", "expand"}]
    return sorted(candidates, key=lambda t: (t.order_key, t.priority))[0] if candidates else None


def task_story(task: Task) -> int:
    return parse_task_id(task.id)[0]


def active_story_scope(tasks: dict[str, Task]) -> int | None:
    active_stories = sorted({
        task_story(task)
        for task in tasks.values()
        if task.status in {"active", "expand", "blocked"}
    })
    return active_stories[0] if active_stories else None


def task_body(title: str, what: str = "", done_when: str = "", why: str = "", how: str = "", constraints: list[str] | None = None) -> str:
    return (
        f"# {title}\n\nWHAT:\n{what}\n\nDONE_WHEN:\n{done_when}\n\nWHY:\n{why}\n\nHOW:\n{how}\n\n"
        + "CONSTRAINTS:\n" + "\n".join(f"- {x}" for x in (constraints or [])) + "\n\nBLOCKER:\nNone\n\nCHILDREN:\n- None\n"
    )


def get_field(body: str, name: str) -> str:
    marker = name + ":"
    pattern = re.compile(r"^" + re.escape(marker) + r"\n(.*?)(?=\n\n[A-Z][A-Z_]*:|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(body)
    return match.group(1).strip() if match else ""



STEP_TRANSITIONS = {
    "queued": {"queued", "ready"},
    "ready": {"ready", "active", "blocked"},
    "active": {"active", "implemented", "blocked"},
    "implemented": {"implemented", "validating"},
    "validating": {"validating", "validated", "failed", "blocked"},
    "failed": {"failed", "ready"},
    "validated": {"validated", "committing"},
    "committing": {"committing", "done", "blocked"},
    "done": {"done"},
    "blocked": {"blocked", "ready"},
}

def transition_step(step: Step, new_status: str) -> None:
    """Apply the manager-owned step lifecycle transition graph."""
    if new_status not in STEP_STATES:
        raise ManagerError("INVALID_STEP_TRANSITION", f"unsupported step state {new_status}", "Use only manager-defined step lifecycle states.")
    allowed = STEP_TRANSITIONS.get(step.status, set())
    if new_status not in allowed:
        raise ManagerError(
            "INVALID_STEP_TRANSITION",
            f"step {step.id} cannot transition from {step.status} to {new_status}",
            "Run 'manager next' and follow the current legal step transition.",
        )
    step.status = new_status

def current_step(store: Store, task: Task) -> Step | None:
    steps = store.load_steps(task.id)
    if task.current_step:
        for step in steps:
            if step.id == task.current_step:
                return step
    for step in steps:
        if step.status in {"ready", "active", "implemented", "validating", "validated", "committing", "failed", "blocked"}:
            return step
    return None



def recover_active_task_with_steps(store: Store, task: Task) -> Task:
    if task.status != "active" or task.phase != "analysis":
        return task
    steps = store.load_steps(task.id)
    if not steps:
        return task
    step = current_step(store, task)
    if step is None:
        step = next((s for s in steps if s.status != "done"), None)
    if step is None:
        return task
    if step.status == "blocked":
        transition_step(step, "ready")
        step.updated = now()
        store.save_step(step)
    task.phase = "implementation"
    task.current_step = step.id
    task.updated = now()
    store.save_task(task)
    return task

def envelope_load_ids(store: Store, task: Task) -> list[str]:
    """Return only manager-resolvable context IDs required by the current phase."""
    if task.phase == "implementation":
        step = current_step(store, task)
        return list(step.load) if step else []
    if task.phase == "planning":
        ids: list[str] = []
        analysis = store.knowledge_dir / f"{task.id}-analysis.md"
        decisions = store.knowledge_dir / f"{task.id}-decisions.md"
        for path in (analysis, decisions):
            if not path.exists():
                continue
            body = path.read_text(encoding="utf-8")
            if path == analysis:
                ids.extend(re.findall(r"^## (FINDING-\d{4})$", body, flags=re.MULTILINE))
            else:
                decision_ids = re.findall(r"^## (DEC-\d{4})$", body, flags=re.MULTILINE)
                for rid in decision_ids:
                    chunk = body.split(f"## {rid}\n", 1)[1].split("\n## ", 1)[0]
                    status = re.search(r"^STATUS:\n([^\n]+)", chunk, flags=re.MULTILINE)
                    latest = status.group(1).strip() if status else ""
                    resolutions = re.findall(
                        r"## DECISION-RESOLUTION-" + re.escape(rid) +
                        r"\n\nDECISION_ID:\n" + re.escape(rid) +
                        r"\n\nSTATUS:\n([^\n]+)", body
                    )
                    if resolutions:
                        latest = resolutions[-1].strip()
                    if latest == "accepted":
                        ids.append(rid)
        return ids
    if task.phase == "final_validation":
        path = store.evidence_dir / f"{task.id}-evidence.md"
        if path.exists():
            return re.findall(r"^## (EVT-\d{4})$", path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    return []


def promote_ready_step(store: Store, task: Task) -> Step | None:
    """Advance the current step through ready -> active at the manager boundary."""
    step = current_step(store, task)
    if step is None or step.status != "ready":
        return step
    steps = store.load_steps(task.id)
    if any(s.status in {"active", "validating", "committing"} and s.id != step.id for s in steps):
        raise ManagerError("CORRUPT_STATE", f"task {task.id} has another executable step while {step.id} is ready", "Restore the managed step lifecycle before continuing.")
    transition_step(step, "active")
    step.updated = now()
    store.save_step(step)
    return step


def next_command_for_phase(phase: str, loads: list[str]) -> str:
    if loads:
        return "manager context"
    if phase in {"analysis", "planning", "implementation", "step_validation", "step_commit", "final_validation", "final_commit"}:
        return "manager submit"
    return "manager next"


def next_envelope_payload(store: Store, task: Task, promote_ready: bool = True) -> dict[str, Any] | None:
    phase = task.phase
    if not phase:
        return None
    role = PHASE_ROLE[phase]
    step = current_step(store, task)
    loads: list[str] = []
    objective = task.title
    action = ""
    accept: list[str] = []
    boundary = ["May edit application repository files explicitly permitted by the current step.", "Must not edit: .manager/**"]
    retry: list[str] = []
    schema: dict[str, Any]

    if phase == "analysis":
        action = "Inspect the task and relevant application material. Produce evidence-backed findings, identify decisions, and determine whether the task is atomic. Do not implement changes."
        accept = ["Relevant evidence is recorded.", "Atomicity is explicitly determined."]
        schema = {"agent_id": "string", "outcome": "completed", "summary": "string", "finding_ids": ["FINDING-0001"], "decision_ids": ["DEC-0001"], "atomic": True, "decomposition_reason": "string, required only when atomic is false"}
    elif phase == "planning":
        loads = envelope_load_ids(store, task)
        action = "Create one ordered implementation plan for this atomic task. Use only the accepted findings and decisions listed in LOAD. Each step must have one bounded action, acceptance criteria, context IDs, edit boundaries, validation commands, and commit policy."
        accept = ["The plan is ordered and bounded.", "Every context reference is reachable.", "Every step has validation and an explicit commit policy."]
        schema = {"agent_id": "string", "steps": [{"title": "string", "action": "string", "accept": ["string"], "load": ["FINDING-0001"], "may_edit": ["src/file.py"], "validation": ["pytest tests/test.py"], "commit_policy": "required", "commit_type": "chore"}], "final_validation": ["pytest"]}
    elif phase == "implementation":
        if promote_ready:
            step = promote_ready_step(store, task)
        if not step:
            raise ManagerError("CORRUPT_STATE", f"active task {task.id} has no current step", "Restore the canonical step records before continuing.")
        loads = step.load
        objective = step.title
        action = step.action
        accept = step.accept
        boundary = ["May edit: " + (", ".join(step.may_edit) if step.may_edit else "none"), "Must not edit: .manager/**"]
        schema = {
            "agent_id": "string",
            "outcome": "completed | blocked",
            "summary": "string",
            "changed_files": ["repository-relative path"],
            "blocker": "string, required only when blocked",
            "evidence": ["string, required only when blocked"],
            "recovery_condition": "string, required only when blocked",
        }
        if step.result == "Validation failed":
            retry = ["manager next"]
    elif phase == "step_validation":
        if not step:
            raise ManagerError("CORRUPT_STATE", f"no current step for {task.id}", "Restore the canonical step records before continuing.")
        objective = step.title
        action = "Run exactly the validation commands listed for the current step. Record actual exit codes and concise observed results. Do not change application behavior to force a pass."
        accept = ["Every required command was executed.", "Every required command passed for a successful result."]
        schema = {"agent_id": "string", "outcome": "passed | failed | blocked", "runs": [{"command": "string", "exit_code": 0, "summary": "string"}], "blocker": "string, required only when blocked"}
    elif phase == "step_commit":
        if not step:
            raise ManagerError("CORRUPT_STATE", f"no current step for {task.id}", "Restore the canonical step records before continuing.")
        objective = step.title
        action = "Verify commit preconditions and request the manager to create the canonical step commit. Do not run git commit yourself."
        accept = ["Current step validation passed.", "Only permitted application files are included."]
        schema = {"agent_id": "string", "outcome": "ready_to_commit | skip_commit"}
    elif phase == "final_validation":
        loads = envelope_load_ids(store, task)
        action = "Review the integrated result against the task completion criteria, inspect the complete relevant diff, and run every final validation command. Use only the evidence listed in LOAD as prior manager-recorded context. Report pass, failure, or blocker with evidence."
        accept = ["All child tasks and implementation steps are complete.", "All final validation commands passed.", "The relevant diff has been reviewed."]
        schema = {"agent_id": "string", "outcome": "passed | failed | blocked", "runs": [{"command": "string", "exit_code": 0, "summary": "string"}], "review_findings": [], "failure_classification": "implementation | planning, required only when failed", "blocker": "string, required only when blocked", "diff_reviewed": True}
    elif phase == "final_commit":
        action = "Verify final commit preconditions and request the manager to create the canonical final commit. Do not run git commit yourself."
        accept = ["All steps are done.", "Final validation passed.", "No unresolved review finding exists."]
        schema = {"agent_id": "string", "outcome": "ready_to_commit"}
    else:
        return None

    return {
        "task": task.id,
        "agent_id": active_task_agent_id(task),
        "task_state": task.status,
        "phase": phase,
        "role": role,
        "step": step.id if step else None,
        "objective": objective,
        "action": action,
        "load": loads,
        "accept": accept,
        "boundary": boundary,
        "return_schema": schema,
        "submit_command": "manager submit",
        "next_command": next_command_for_phase(phase, loads),
        "output_limit": MAX_SUBMITTED_TEXT,
        "recommended_context_command": f"manager context --compact --max-chars {DEFAULT_CONTEXT_MAX_CHARS}",
        "micro_cycle": MICRO_CYCLE,
        "retry": retry,
        "rules": [
            "Perform only ACTION.",
            "Do not create or edit manager-owned files.",
            "Do not start another task or step.",
            "Use AGENT_ID from this envelope in every task interaction payload.",
            RESEARCH_REMINDER,
        ],
    }


def render_next_envelope(payload: dict[str, Any], as_json: bool = False) -> str:
    if as_json:
        return json.dumps(payload, indent=2)
    lines = [
        f"TASK: {payload['task']}",
        f"AGENT_ID: {payload['agent_id']}",
        f"TASK_STATE: {payload['task_state']}",
        f"PHASE: {payload['phase']}",
        f"ROLE: {payload['role']}",
    ]
    if payload.get("step"):
        lines.append(f"STEP: {payload['step']}")
    lines += ["", "OBJECTIVE:", payload["objective"], "", "ACTION:", payload["action"], "", "LOAD:"]
    lines += [f"- {x}" for x in payload["load"]] if payload["load"] else ["- None"]
    lines += ["", "ACCEPT:"] + [f"- {x}" for x in payload["accept"]]
    lines += ["", "BOUNDARY:"] + [f"- {x}" for x in payload["boundary"]]
    lines += ["", "NEXT_COMMAND:", payload["next_command"]]
    lines += ["", "RETURN_SCHEMA:", json.dumps(payload["return_schema"], indent=2)]
    lines += ["", "RETURN_SCHEMA_PATH:", payload["return_schema_path"]]
    lines += ["", "OUTPUT_LIMIT:", f"{payload['output_limit']} characters per textual result field"]
    if payload.get("retry"):
        lines += ["", "RETRY:"] + payload["retry"]
    lines += ["", "SUBMIT:", payload["submit_command"], "", "RULES:"] + [f"- {x}" for x in payload["rules"]]
    return "\n".join(lines) + "\n"


def next_envelope(store: Store, task: Task, as_json: bool = False, promote_ready: bool = True) -> str:
    payload = next_envelope_payload(store, task, promote_ready=promote_ready)
    if not payload:
        return "NO_TASK"
    payload["return_schema_path"] = persist_return_schema(store, payload["return_schema"])
    return render_next_envelope(payload, as_json=as_json)


def transition_task(task: Task, new_status: str) -> None:
    """Apply a manager-owned task lifecycle transition."""
    if new_status not in TASK_STATES:
        raise ManagerError("INVALID_TRANSITION", f"unsupported task state {new_status}", "Use only manager-defined task lifecycle states.")
    allowed = TASK_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise ManagerError(
            "INVALID_TRANSITION",
            f"task {task.id} cannot transition from {task.status} to {new_status}",
            f"Run 'manager next' and follow the current legal transition for {task.id}.",
        )
    task.status = new_status


def ensure_story_scope_before_transition(tasks: dict[str, Task], task: Task, new_status: str) -> None:
    if new_status not in STORY_ACTIVE_STATES:
        return
    target_story = parse_task_id(task.id)[0]
    conflicting = sorted(
        [
            other
            for other in tasks.values()
            if other.id != task.id
            and other.status in STORY_ACTIVE_STATES
            and parse_task_id(other.id)[0] != target_story
        ],
        key=lambda t: t.order_key,
    )
    if conflicting:
        owner = conflicting[0]
        owner_story = parse_task_id(owner.id)[0]
        raise ManagerError(
            "STORY_SCOPE_CONFLICT",
            f"cannot move {task.id} to {new_status} while story S{owner_story:05d} has {owner.status} task {owner.id}",
            f"Complete, unblock, or administratively repair story S{owner_story:05d} before changing story S{target_story:05d}.",
        )


def checkpoint_preexisting_changes(store: Store, task: Task) -> None:
    if not store.git_info()[0]:
        return
    preexisting = [p for p in store.git_status_paths() if p != ".manager" and not p.startswith(".manager/")]
    if preexisting:
        try:
            store.git_commit(preexisting, f"chore: checkpoint before activating {task.id}")
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ManagerError(
                "DIRTY_WORKTREE",
                "working tree contains pre-existing application changes and automatic checkpoint commit failed",
                "Commit or stash application changes manually, then run 'manager next' again.",
            ) from exc
    task.git_base = []
    task.git_base_head = store.git_head()


def activate_task(store: Store, task: Task) -> None:
    tasks = store.load_tasks()
    if task.status != "planned":
        return
    if any(t.status == "active" and t.id != task.id for t in tasks.values()):
        raise ManagerError("ACTIVE_TASK_EXISTS", "another task is already active", "Run 'manager next' and continue the active task before starting another.")
    ensure_story_scope_before_transition(tasks, task, "active")
    checkpoint_preexisting_changes(store, task)
    transition_task(task, "active"); task.phase = "analysis"; task.updated = now(); store.save_task(task)


def activate_expanded(store: Store, task: Task) -> None:
    tasks = store.load_tasks()
    children = store.children(store.load_tasks(), task.id)
    if not children:
        raise ManagerError("INVALID_DECOMPOSITION", f"expanded task {task.id} has no children", "Create at least one child task before continuing.")
    if not all(c.status == "done" for c in children):
        raise ManagerError("CHILDREN_INCOMPLETE", f"expanded task {task.id} cannot resume until all children are done", "Run 'manager next' to work the remaining child task.")
    ensure_story_scope_before_transition(tasks, task, "active")
    checkpoint_preexisting_changes(store, task)
    transition_task(task, "active"); task.phase = "final_validation"; task.updated = now(); store.save_task(task)


def cmd_next(store: Store, as_json: bool = False) -> str:
    with store.lock():
        store.initialize()
        tasks = store.load_tasks()
        active = [t for t in tasks.values() if t.status == "active"]
        if active:
            active_task = recover_active_task_with_steps(store, sorted(active, key=lambda t: t.order_key)[0])
            store.rebuild_index()
            return next_envelope(store, active_task, as_json=as_json)

        scope_story = active_story_scope(tasks)
        if scope_story is None:
            selectable_stories = sorted({
                task_story(task)
                for task in tasks.values()
                if task.status in {"planned", "expand"}
            })
            scope_story = selectable_stories[0] if selectable_stories else None
        if scope_story is None:
            return no_task_payload(store)

        scoped_tasks = [t for t in tasks.values() if task_story(t) == scope_story]
        candidates = [t for t in scoped_tasks if t.status == "planned"]
        # An expanded parent is a coordination node. Its actionable children are selected
        # before the parent can resume final integration.
        for parent in sorted([t for t in scoped_tasks if t.status == "expand"], key=lambda t: t.order_key):
            children = store.children(tasks, parent.id)
            candidates.extend(c for c in children if c.status == "planned")
        candidates = sorted(candidates, key=lambda t: (t.order_key, t.priority))
        if not candidates:
            expanded = sorted([t for t in scoped_tasks if t.status == "expand"], key=lambda t: t.order_key)
            if expanded and all(c.status == "done" for c in store.children(tasks, expanded[0].id)):
                task = expanded[0]
                activate_expanded(store, task)
                store.rebuild_index()
                return next_envelope(store, task, as_json=as_json)
            return no_task_payload(store)
        task = candidates[0]
        activate_task(store, task)
        store.rebuild_index()
        return next_envelope(store, task, as_json=as_json)

def cmd_context(store: Store, ref: str | None, compact: bool = False, max_chars: int = DEFAULT_CONTEXT_MAX_CHARS, as_json: bool = False) -> str:
    if max_chars < 200 or max_chars > MAX_SUBMITTED_TEXT:
        raise ManagerError("INVALID_CONTEXT_LIMIT", "max_chars must be between 200 and 8000", "Use --max-chars with a value from 200 through 8000.")
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = selected_task(store, tasks)
        if not task or task.status != "active": return "NO_TASK"
        step = current_step(store, task)
        allowed = set(envelope_load_ids(store, task))
        if ref:
            if ref.startswith(task.id + "/"):
                local = ref.split("/", 1)[1]
            else:
                local = ref
            if local not in allowed:
                raise ManagerError("UNREACHABLE_CONTEXT", f"context ID {ref} is not reachable from the current envelope", "Run 'manager next' and load only IDs listed in LOAD.")
            refs = [local]
        else:
            refs = list(allowed)
        out: list[str] = []
        records: list[dict[str, Any]] = []
        for rid in refs:
            if rid.startswith("FINDING-"):
                path = store.knowledge_dir / f"{task.id}-analysis.md"
                record = resolve_record(path, rid, "finding", compact=compact, max_chars=max_chars)
            elif rid.startswith("DEC-"):
                path = store.knowledge_dir / f"{task.id}-decisions.md"
                record = resolve_record(path, rid, "decision", compact=compact, max_chars=max_chars)
            elif rid.startswith("EVT-"):
                path = store.evidence_dir / f"{task.id}-evidence.md"
                record = resolve_record(path, rid, "evidence", compact=compact, max_chars=max_chars)
            else:
                raise ManagerError("INVALID_CONTEXT_ID", f"unsupported context ID {rid}", "Use only stable FINDING, DEC, or EVT IDs returned by the manager.")
            out.append(record["text"])
            records.append({"id": record["id"], "type": record["type"], "content": record["content"], "compact": compact})
        if as_json:
            return json.dumps({
                "task": task.id,
                "phase": task.phase,
                "compact": compact,
                "max_chars": max_chars,
                "records": records,
            }, indent=2)
        header = [f"TASK: {task.id}", f"PHASE: {task.phase}", ""]
        return "\n".join(header + [x for x in out if x]) or "NO_CONTEXT"


def resolve_record(path: Path, rid: str, typ: str, compact: bool = False, max_chars: int = DEFAULT_CONTEXT_MAX_CHARS) -> dict[str, str]:
    if not path.exists():
        raise ManagerError("MISSING_CONTEXT", f"context record {rid} is unavailable", "Use 'manager next' to refresh the current envelope and load only reachable records.")
    _, body = __import__("manager.core", fromlist=["parse_frontmatter"]).parse_frontmatter(path.read_text(encoding="utf-8"))
    marker = "## " + rid
    if marker not in body:
        raise ManagerError("MISSING_CONTEXT", f"context record {rid} is unavailable", "Use 'manager next' to refresh the current envelope.")
    chunk = body.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    if typ == "decision":
        resolutions = re.findall(r"## DECISION-RESOLUTION-" + re.escape(rid) + r"\n\nDECISION_ID:\n" + re.escape(rid) + r"\n\nSTATUS:\n([^\n]+)", body)
        if resolutions:
            chunk += "\n\nSTATUS:\n" + resolutions[-1].strip()
    if compact:
        text = compact_context_record(rid, typ, chunk, max_chars)
        return {"id": rid, "type": typ, "content": text.rstrip(), "text": text}
    text = f"CONTEXT: {rid}\nTYPE: {typ}\n{chunk}\n"
    return {"id": rid, "type": typ, "content": chunk, "text": text}


def cmd_task_add(store: Store, args: argparse.Namespace) -> str | dict[str, Any]:
    payload = stdin_json()
    task_fields = {"title", "what", "done_when", "why", "how", "constraints", "parent", "priority"}
    batch_items: list[dict[str, Any]] | None = None
    force_new_story = bool(args.new_story)

    if "items" in payload:
        ensure_keys(payload, {"items"}, {"items"})
        items = require_list(payload["items"], "items", True)
        validated_items: list[dict[str, Any]] = []
        for index, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ManagerError("INVALID_SCHEMA", f"items[{index}] must be an object", "Provide every batch item as a JSON object.")
            ensure_keys(item, task_fields, {"title"})
            validated_items.append(item)
        batch_items = validated_items
        force_new_story = len(validated_items) > 1
    else:
        ensure_keys(payload, task_fields, {"title"})
        batch_items = [payload]

    for index, item in enumerate(batch_items, 1):
        priority_value = item.get("priority", 3)
        if not isinstance(priority_value, int) or isinstance(priority_value, bool):
            raise ManagerError("INVALID_SCHEMA", f"items[{index}].priority must be an integer", "Provide an integer priority from 0 through 99.")
        if not 0 <= priority_value <= 99:
            raise ManagerError("INVALID_TASK", f"items[{index}].priority must be between 0 and 99", "Provide a priority from 0 through 99.")
        for field_name in ("what", "done_when", "why", "how"):
            if field_name in item and item[field_name] is not None and not isinstance(item[field_name], str):
                raise ManagerError("INVALID_SCHEMA", f"items[{index}].{field_name} must be a string", f"Provide items[{index}].{field_name} as a string.")
        if "constraints" in item and item["constraints"] is not None:
            require_string_list(item["constraints"], f"items[{index}].constraints")

    with store.lock():
        store.initialize()
        tasks = store.load_tasks()
        norm = lambda x: " ".join(x.casefold().split())
        unfinished_by_title = {norm(task.title): task.id for task in tasks.values() if task.status != "done"}
        requested_titles: set[str] = set()
        created: list[dict[str, str]] = []

        for index, item in enumerate(batch_items, 1):
            title = require_str(item["title"], f"items[{index}].title")
            normalized_title = norm(title)
            if normalized_title in unfinished_by_title:
                dup_id = unfinished_by_title[normalized_title]
                raise ManagerError("DUPLICATE_TASK", f"unfinished task already exists as {dup_id}", f"Continue with {dup_id} instead of creating a duplicate.")
            if normalized_title in requested_titles:
                raise ManagerError("DUPLICATE_TASK", f"items[{index}] duplicates another requested title", "Use one unique title per requested item.")

            parent = item.get("parent")
            if parent is not None:
                if force_new_story:
                    raise ManagerError("INVALID_PARENT", "parent is not allowed when adding multiple items", "Remove parent from batch items because each item becomes a new story.")
                parent = require_str(parent, "parent")
                pt = tasks.get(parent)
                if not pt or pt.status != "expand":
                    raise ManagerError("INVALID_PARENT", f"parent {parent} must be in expand state", "Expand a valid parent before adding a child.")

            tid = store.allocate_task_id(tasks, parent=parent, new_story=force_new_story)
            what = item.get("what", "").strip()
            done_when = item.get("done_when", "").strip()
            planned = bool(what and done_when)
            body = task_body(
                title,
                what,
                done_when,
                item.get("why", "").strip(),
                item.get("how", "").strip(),
                item.get("constraints") or [],
            )
            task = Task(
                store.tasks_dir / "placeholder.md",
                tid,
                title,
                parent,
                task_sequence_for_id(tid),
                int(item.get("priority", 3)),
                "planned" if planned else "draft",
                None,
                None,
                store.commit_mode(),
                "",
                now(),
                now(),
                agent_id=generated_agent_id(tid),
                body=body,
            )
            store.save_task(task)
            tasks[task.id] = task
            unfinished_by_title[normalized_title] = task.id
            requested_titles.add(normalized_title)
            created.append({"id": tid, "status": task.status, "title": title})

        store.rebuild_index()
        if len(created) == 1:
            item = created[0]
            return f"CREATED {item['id']} {item['status']} {item['title']}"
        return {
            "result": "CREATED_BATCH",
            "count": len(created),
            "created": created,
            "note": "Multiple requested items were split into individual stories/tasks before implementation.",
        }


def cmd_task_edit(store: Store, task_id: str | None) -> str:
    p = stdin_json()
    ensure_keys(p, {"task", "title", "what", "done_when", "why", "how", "constraints"}, {"title", "what", "done_when"})
    title = require_str(p["title"], "title")
    what = require_str(p["what"], "what")
    done_when = require_str(p["done_when"], "done_when")
    with store.lock():
        store.initialize()
        tasks = store.load_tasks()
        tid = task_id or p.get("task")
        task = tasks.get(tid) if tid else selected_task(store, tasks)
        if not task:
            raise ManagerError("NO_TASK", "task was not found", "Provide an existing task ID.")
        if task.status not in {"draft", "planned"}:
            raise ManagerError("INVALID_EDIT", f"task {task.id} cannot be edited from {task.status}", "Edit task definition only while it is draft or planned.")
        task.title = title
        task.body = task_body(title, what, done_when, str(p.get("why", "")).strip(), str(p.get("how", "")).strip(), p.get("constraints") or [])
        if task.status == "draft":
            transition_task(task, "planned")
        task.updated = now()
        store.save_task(task); store.rebuild_index()
        return f"OK {task.id} {task.status}"


def cmd_plan_task(store: Store, task_id: str | None) -> str:
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(task_id) if task_id else next((t for t in sorted(tasks.values(), key=lambda x:x.order_key) if t.status == "draft"), None)
        if not task: raise ManagerError("NO_TASK", "no draft task is available", "Create a task with 'manager task add' or provide a draft task ID.")
        if task.status != "draft": return f"OK {task.id} already {task.status}"
        what, done = get_field(task.body, "WHAT"), get_field(task.body, "DONE_WHEN")
        if not what or not done:
            raise ManagerError("INVALID_TASK", f"task {task.id} cannot be planned without WHAT and DONE_WHEN", "Edit the task with both WHAT and DONE_WHEN, then rerun planning.")
        transition_task(task, "planned"); task.updated = now(); store.save_task(task); store.rebuild_index(); return f"OK {task.id} planned"


def cmd_task_expand(store: Store, task_id: str | None) -> str:
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(task_id) if task_id else selected_task(store, tasks)
        if not task: raise ManagerError("NO_TASK", "no task is available to expand", "Run 'manager next' or provide a task ID.")
        if task.status not in {"planned", "active"}: raise ManagerError("INVALID_TRANSITION", f"task {task.id} cannot enter expand from {task.status}", "Expand only a planned or active task.")
        if task.status == "active" and task.phase not in {"analysis", "planning"}:
            raise ManagerError("INVALID_TRANSITION", f"active task {task.id} cannot enter expand from phase {task.phase}", "Decompose an active task only from its analysis or planning phase.")
        ensure_story_scope_before_transition(tasks, task, "expand")
        transition_task(task, "expand"); task.phase = None; task.updated = now(); store.save_task(task); store.rebuild_index(); return f"OK {task.id} expand"


def cmd_task_block(store: Store, task_id: str | None) -> str:
    reason = sys.stdin.read().strip()
    if not reason: raise ManagerError("INVALID_BLOCKER", "blocker reason is required", "Provide a non-empty blocker reason on stdin.")
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(task_id) if task_id else selected_task(store, tasks)
        if not task: raise ManagerError("NO_TASK", "no task is available to block", "Run 'manager next' or provide a task ID.")
        if task.status not in {"draft", "planned", "active", "expand", "blocked"}: raise ManagerError("INVALID_TRANSITION", f"task {task.id} cannot be blocked from {task.status}", "Block only a non-terminal task.")
        ensure_story_scope_before_transition(tasks, task, "blocked")
        # A task-level block must also terminate the currently executable step
        # when the active phase owns one. Otherwise the task becomes inactive
        # while an implementation/validation/commit step remains executable,
        # violating the execution-state consistency invariant.
        if task.status == "active" and task.current_step and task.phase in {"implementation", "step_validation", "step_commit"}:
            step = next((s for s in store.load_steps(task.id) if s.id == task.current_step), None)
            if step is None:
                raise ManagerError("CORRUPT_STATE", f"active task {task.id} references missing current step {task.current_step}", "Restore the canonical current step before blocking the task.")
            transition_step(step, "blocked")
            step.result = reason
            step.updated = now()
            store.save_step(step)
        transition_task(task, "blocked"); task.phase = None; task.blocker = reason; task.updated = now(); store.save_task(task); store.rebuild_index(); return f"OK {task.id} blocked"


def cmd_task_unblock(store: Store, task_id: str | None) -> str:
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(task_id) if task_id else next((t for t in sorted(tasks.values(), key=lambda x:x.order_key) if t.status == "blocked"), None)
        if not task: raise ManagerError("NO_TASK", "no blocked task is available", "Provide a blocked task ID or create a blocked task.")
        if task.status != "blocked": raise ManagerError("INVALID_TRANSITION", f"task {task.id} is not blocked", "Unblock only a blocked task.")
        transition_task(task, "planned"); task.phase = None; task.blocker = ""; task.updated = now(); store.save_task(task); store.rebuild_index(); return f"OK {task.id} planned"


def cmd_finding_add(store: Store) -> str:
    p = stdin_json(); ensure_keys(p, {"task", "agent_id", "question", "finding", "evidence", "impact", "confidence", "submission_token"}, {"agent_id", "question", "finding", "evidence", "impact", "confidence"})
    for f in ("question", "finding", "impact", "confidence"): require_str(p[f], f)
    ev = require_string_list(p["evidence"], "evidence", True); token = optional_token(p.get("submission_token"))
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(p.get("task")) if p.get("task") else selected_task(store, tasks)
        if not task or task.status != "active" or task.phase != "analysis": raise ManagerError("INVALID_PHASE", "findings can only be added during analysis", "Run 'manager next' and follow the current analysis envelope.")
        require_payload_agent_id(p, task)
        ev = enrich_file_evidence_list(store, ev)
        if token:
            existing = store.load_submissions().get(token)
            if existing: return store.remember_submission(token, p, existing.response)
        fid = f"FINDING-{store.next_record_number(task.id, 'FINDING'):04d}"
        path = store.knowledge_dir / f"{task.id}-analysis.md"
        fm = {"type":"analysis","format_version":FORMAT_VERSION,"id":f"{task.id}-ANALYSIS","task_id":task.id,"created":now(),"updated":now()}
        section = f"## {fid}\n\nQUESTION:\n{p['question'].strip()}\n\nFINDING:\n{p['finding'].strip()}\n\nEVIDENCE:\n" + "\n".join(f"- {x}" for x in ev) + f"\n\nIMPACT:\n{p['impact'].strip()}\n\nCONFIDENCE:\n{p['confidence'].strip()}\n"
        store.append_record(path, fm, f"# Analysis for {task.id}\n\n" + section if not path.exists() else section)
        task.analysis = f"../knowledge/{path.name}"; task.updated = now(); store.save_task(task); store.rebuild_index()
        return store.remember_submission(token, p, fid) if token else fid


def cmd_decision_propose(store: Store) -> str:
    p = stdin_json(); ensure_keys(p, {"task", "agent_id", "decision","rationale","alternatives","consequences","evidence","supersedes","submission_token"}, {"agent_id", "decision","rationale","alternatives","consequences","evidence"})
    for f in ("decision", "rationale"): require_str(p[f], f)
    alts = require_list(p["alternatives"], "alternatives"); cons = require_list(p["consequences"], "consequences", True); evidence = require_list(p["evidence"], "evidence", True); token = optional_token(p.get("submission_token"))
    for a in alts:
        if not isinstance(a, dict) or set(a) != {"option", "reason_rejected"}: raise ManagerError("INVALID_SCHEMA", "each alternative must contain option and reason_rejected", "Resubmit alternatives using the exact decision schema.")
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(p.get("task")) if p.get("task") else selected_task(store, tasks)
        if not task or task.status != "active" or task.phase != "analysis": raise ManagerError("INVALID_PHASE", "decisions can only be proposed during analysis", "Run 'manager next' and follow the current analysis envelope.")
        require_payload_agent_id(p, task)
        evidence = enrich_file_evidence_list(store, [str(x) for x in evidence])
        if token and token in store.load_submissions(): return store.remember_submission(token, p, store.load_submissions()[token].response)
        did = f"DEC-{store.next_record_number(task.id, 'DEC'):04d}"; path = store.knowledge_dir / f"{task.id}-decisions.md"; fm={"type":"decisions","format_version":FORMAT_VERSION,"id":f"{task.id}-DECISIONS","task_id":task.id,"created":now(),"updated":now()}
        supersedes = p.get("supersedes")
        if supersedes is not None:
            supersedes = require_str(supersedes, "supersedes")
            if not supersedes.startswith("DEC-"):
                raise ManagerError("INVALID_DECISION", "supersedes must reference a decision ID", "Reference an existing accepted DEC-#### decision.")
            existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
            if f"## {supersedes}\n" not in existing_text:
                raise ManagerError("MISSING_DECISION", f"decision {supersedes} does not exist", "Supersede only an existing accepted decision.")
            old_chunk = existing_text.split(f"## {supersedes}\n", 1)[1].split("\n## ", 1)[0]
            resolutions = re.findall(r"## DECISION-RESOLUTION-" + re.escape(supersedes) + r"\n\nDECISION_ID:\n" + re.escape(supersedes) + r"\n\nSTATUS:\n([^\n]+)", existing_text)
            latest_status = resolutions[-1].strip() if resolutions else ("proposed" if "STATUS:\nproposed" in old_chunk else "")
            if latest_status != "accepted":
                raise ManagerError("INVALID_DECISION", f"decision {supersedes} is not accepted", "Only an accepted decision may be superseded.")
        section = f"## {did}\n\nSTATUS:\nproposed\n\nDECISION:\n{p['decision']}\n\nRATIONALE:\n{p['rationale']}\n\nALTERNATIVES:\n" + "\n".join(f"- {a['option']}: {a['reason_rejected']}" for a in alts) + "\n\nCONSEQUENCES:\n" + "\n".join(f"- {x}" for x in cons) + "\n\nEVIDENCE:\n" + "\n".join(f"- {x}" for x in evidence) + f"\n\nSUPERSEDES:\n{supersedes or 'None'}\n"
        # A superseding decision is only a proposal at this point. The prior
        # accepted decision remains accepted until the replacement itself is
        # accepted. This preserves the specified decision lifecycle:
        # proposed -> accepted|rejected and accepted -> superseded.
        store.append_record(path, fm, f"# Decisions for {task.id}\n\n" + section if not path.exists() else section)
        task.decisions=f"../knowledge/{path.name}"; task.updated=now(); store.save_task(task); store.rebuild_index(); return store.remember_submission(token,p,did) if token else did


def cmd_evidence_add(store: Store) -> str:
    p = stdin_json()
    ensure_keys(p, {"task", "agent_id", "type", "fields", "submission_token"}, {"agent_id", "type", "fields"})
    typ = require_str(p["type"], "type")
    fields = p["fields"]
    if not isinstance(fields, dict) or not fields:
        raise ManagerError("INVALID_SCHEMA", "fields must be a non-empty object", "Submit evidence fields as a non-empty JSON object.")
    token = optional_token(p.get("submission_token"))
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(p.get("task")) if p.get("task") else selected_task(store, tasks)
        if not task:
            raise ManagerError("NO_TASK", "task was not found", "Provide an existing task ID or run 'manager next'.")
        require_payload_agent_id(p, task)
        if token and token in store.load_submissions():
            return store.remember_submission(token, p, store.load_submissions()[token].response)
        safe_fields = {}
        for key, value in fields.items():
            if not isinstance(key, str) or not key.strip():
                raise ManagerError("INVALID_SCHEMA", "evidence field names must be non-empty strings", "Use simple string field names.")
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                value = enrich_file_evidence_list(store, [str(item) for item in value])
            text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
            reject_secret(text, f"evidence.{key}")
            safe_fields[key] = text
        eid = append_evidence(store, task, typ, safe_fields)
        return store.remember_submission(token, p, eid) if token else eid


def validate_refs_for_plan(task: Task, store: Store, refs: list[str]) -> None:
    for ref in refs:
        rid = ref.split("/", 1)[-1]
        if rid.startswith("FINDING-"):
            p = store.knowledge_dir / f"{task.id}-analysis.md"
        elif rid.startswith("DEC-"):
            p = store.knowledge_dir / f"{task.id}-decisions.md"
        else:
            raise ManagerError("UNREACHABLE_CONTEXT", f"unsupported knowledge reference {ref}", "Reference only accepted FINDING or DEC records for planning.")
        if not p.exists() or ("## " + rid) not in p.read_text(encoding="utf-8"):
            raise ManagerError("UNREACHABLE_CONTEXT", f"knowledge reference {ref} does not exist", "Use only IDs returned by accepted analysis records.")
        if rid.startswith("DEC-"):
            record = resolve_record(p, rid, "decision")
            if "STATUS:\naccepted" not in record["content"]:
                raise ManagerError("UNRESOLVED_DECISION", f"decision {rid} is not accepted", "Resolve the decision before using it in a plan.")


def cmd_plan_submit(store: Store, task: Task, p: dict[str, Any]) -> str:
    ensure_keys(p, {"agent_id", "steps","final_validation","submission_token"}, {"agent_id", "steps","final_validation"})
    require_payload_agent_id(p, task)
    raw_steps = require_list(p["steps"], "steps", True); final_validation = require_list(p["final_validation"], "final_validation", True)
    if any(not isinstance(x, dict) for x in raw_steps): raise ManagerError("INVALID_SCHEMA", "every step must be an object", "Resubmit a plan containing only step objects.")
    existing = store.load_steps(task.id)
    if existing and not all(step.status in {"done", "failed", "blocked"} for step in existing): raise ManagerError("PLAN_EXISTS", f"task {task.id} already has an active plan", "Continue with the existing plan instead of replacing it.")
    titles: set[str] = set()
    actions: set[str] = set()
    for i, x in enumerate(raw_steps, 1):
        allowed={"title","action","accept","load","may_edit","validation","commit_policy","commit_type"}
        ensure_keys(x, allowed, allowed)
        title=require_str(x["title"],"step.title"); action=require_str(x["action"],"step.action")
        if title.casefold() in titles: raise ManagerError("INVALID_PLAN", f"duplicate step title at sequence {i}", "Each step must have a unique bounded action.")
        titles.add(title.casefold()); accept=require_list(x["accept"],"step.accept",True); load=require_list(x["load"],"step.load"); may_edit=require_list(x["may_edit"],"step.may_edit"); validation=require_list(x["validation"],"step.validation",True)
        action_key=" ".join(action.casefold().split())
        if action_key in actions: raise ManagerError("INVALID_PLAN", f"duplicate action at sequence {i}", "Each implementation step must perform a distinct bounded action.")
        actions.add(action_key)
        if x["commit_policy"] not in {"required","optional","disabled"}: raise ManagerError("INVALID_PLAN", "commit_policy must be required, optional, or disabled", "Use one of the supported commit policies.")
        if x["commit_type"] not in {"chore","fix","refactor","test","docs"}: raise ManagerError("INVALID_PLAN", "unsupported commit_type", "Use chore, fix, refactor, test, or docs.")
        for path in may_edit:
            try: rel_safe(path)
            except ValueError as exc: raise ManagerError("INVALID_PATH", str(exc), "Remove traversal, absolute paths, and .manager paths from MAY_EDIT.")
            if path == ".manager" or path.startswith(".manager/"):
                raise ManagerError("INVALID_PATH", f"step {i} may not edit .manager", "Remove .manager paths from MAY_EDIT.")
        validation = [validate_command(v, "step.validation") for v in validation]
        if not validation:
            raise ManagerError("INVALID_PLAN", f"step {i} has no validation command", "Add at least one exact validation command to every implementation step.")
        final_validation = [validate_command(v, "final_validation") for v in final_validation]
        validate_refs_for_plan(task, store, load)
    with store.lock():
        # Recheck under lock because planning is a mutation.
        store.initialize(); tasks=store.load_tasks(); task=tasks[task.id]
        if task.phase != "planning": raise ManagerError("INVALID_PHASE", "task is no longer in planning", "Run 'manager next' to obtain the current phase.")
        if existing:
            archive_existing_steps(store, task.id, existing)
        # Step identifiers are durable record identities, not plan-local
        # sequence numbers. Replanning must never reuse archived STEP IDs.
        first_step_number = store.next_step_number(task.id)
        for i,x in enumerate(raw_steps,1):
            step_id = f"STEP-{first_step_number + i - 1:04d}"
            step=Step(step_id,task.id,i,"ready" if i==1 else "queued",PHASE_ROLE["implementation"],str(x["title"]).strip(),str(x["action"]).strip(),list(map(str,x["accept"])),list(map(str,x["load"])),list(map(str,x["may_edit"])),list(map(str,x["validation"])),str(x["commit_policy"]),str(x["commit_type"]),now(),now())
            store.save_step(step)
        task.final_validation=list(map(str,final_validation)); task.current_step=f"STEP-{first_step_number:04d}"; task.phase="implementation"; task.updated=now(); store.save_task(task); store.rebuild_index(); return f"OK {task.id} plan accepted"


def archive_existing_steps(store: Store, task_id: str, existing_steps: list[Step]) -> None:
    stamp = now().replace(":", "-")
    base = store.archive_dir / task_id
    archive_dir = base / stamp
    suffix = 1
    while archive_dir.exists():
        archive_dir = base / f"{stamp}-{suffix:02d}"
        suffix += 1
    archive_dir.mkdir(parents=True, exist_ok=False)
    for old_step in existing_steps:
        old_path = store.steps_dir / f"{task_id}-{old_step.id}.md"
        if not old_path.exists():
            continue
        dest = archive_dir / old_path.name
        if dest.exists():
            stem, ext = old_path.stem, old_path.suffix
            i = 1
            while (archive_dir / f"{stem}-{i:02d}{ext}").exists():
                i += 1
            dest = archive_dir / f"{stem}-{i:02d}{ext}"
        shutil.move(str(old_path), str(dest))


def append_evidence(store: Store, task: Task, event_type: str, fields: dict[str, Any]) -> str:
    eid=f"EVT-{store.next_record_number(task.id,'EVT'):04d}"; path=store.evidence_dir/f"{task.id}-evidence.md"; fm={"type":"evidence","format_version":FORMAT_VERSION,"id":f"{task.id}-EVIDENCE","task_id":task.id,"created":now(),"updated":now()}
    section=f"## {eid}\n\nTYPE:\n{event_type}\n\nRECORDED_AT:\n{now()}\n"+"\n".join(f"\n{k.upper()}:\n{v}" for k,v in fields.items())+"\n"
    store.append_record(path,fm,f"# Evidence for {task.id}\n\n"+section if not path.exists() else section); task.evidence=f"../evidence/{path.name}"; task.updated=now(); store.save_task(task); return eid


def verify_changed_files(store: Store, task: Task, step: Step, changed: list[str]) -> None:
    declared=[]
    for p in changed: declared.append(rel_safe(p))
    allowed=set(step.may_edit)
    bad=sorted(set(declared)-allowed)
    if bad: raise ManagerError("BOUNDARY_VIOLATION", "reported changed files outside the step boundary: " + ", ".join(bad), "Revert or exclude unauthorized changes and resubmit only files permitted by the current step.")
    if store.git_info()[0]:
        current=set(store.git_status_paths())
        missing=[p for p in declared if not (store.root / p).exists() and p not in current]
        if missing:
            raise ManagerError("MISSING_CHANGED_FILE", "reported changed files do not exist or are not represented by the Git worktree: " + ", ".join(missing), "Ensure the implementation produced the reported files or report the exact Git-tracked deletion path before resubmitting.")
    else:
        missing=[p for p in declared if not (store.root / p).exists()]
        if missing:
            raise ManagerError("MISSING_CHANGED_FILE", "reported changed files do not exist: " + ", ".join(missing), "Ensure the implementation produced the reported files before resubmitting.")
        current=set()
    if store.git_info()[0]:
        base=set(task.git_base)
        new=current-base
        # A submitted changed_files list must describe the actual current Git
        # worktree delta, not merely paths that happen to exist. This prevents a
        # model from claiming a reverted/no-op file as changed and makes the
        # implementation-result record auditable against Git. Tracked deletions
        # remain valid because Git status contains their path even though the
        # filesystem path no longer exists.
        missing_from_diff=sorted(set(declared)-new)
        if missing_from_diff:
            raise ManagerError(
                "CHANGED_FILE_NOT_IN_DIFF",
                "reported changed files are not present in the current Git worktree diff: " + ", ".join(missing_from_diff),
                "Report only files actually changed by the current implementation, then resubmit the exact changed_files list.",
            )
        # Managed state changes are not application changes, but must never be
        # part of step changes.
        undeclared=sorted(new-set(declared))
        if undeclared:
            raise ManagerError(
                "UNDECLARED_CHANGES",
                "repository changes were not reported: " + ", ".join(undeclared),
                "Include every current application change in changed_files or restore unrelated changes before resubmitting.",
            )


def command_allowed(command: str, allowed: list[str]) -> bool:
    return command in allowed


def recover_step_commit(store: Store, task: Task, step: Step) -> str | None:
    if task.commit_mode != "enabled" or not step.commit_message or step.commit_id:
        return None
    try:
        if store.git_head_subject() != step.commit_message:
            return None
        cid = store.git_head()
        if step.commit_base_head and store.git(["rev-parse", f"{cid}^"], check=False).stdout.strip() != step.commit_base_head:
            return None
        paths = set(store.git_commit_paths())
        expected = set(step.may_edit)
        if not paths.issubset(expected):
            return None
    except (ManagerError, subprocess.SubprocessError):
        return None
    step.commit_id = cid
    transition_step(step, "done")
    step.updated = now()
    store.save_step(step)
    append_evidence(store, task, "commit_recovered", {"STEP": step.id, "COMMIT_ID": cid, "MESSAGE": step.commit_message})
    advance_after_step(store, task, step)
    return cid


def recover_final_commit(store: Store, task: Task) -> str | None:
    if task.commit_mode != "enabled" or not task.final_commit_message or task.final_commit_id:
        return None
    try:
        if store.git_head_subject() != task.final_commit_message:
            return None
        cid = store.git_head()
        if task.git_base_head and store.git(["rev-parse", f"{cid}^"], check=False).stdout.strip() != task.git_base_head:
            return None
        steps = store.load_steps(task.id)
        allowed = {path for step in steps for path in step.may_edit}
        committed = set(store.git_commit_paths(cid))
        if not committed.issubset(allowed):
            return None
    except (ManagerError, subprocess.SubprocessError):
        return None
    task.final_commit_id = cid
    transition_task(task, "done")
    task.phase = None
    task.current_step = None
    task.updated = now()
    store.save_task(task)
    append_evidence(store, task, "final_commit_recovered", {"COMMIT_ID": cid, "MESSAGE": task.final_commit_message})
    store.rebuild_index()
    return cid


def cmd_submit(store: Store) -> str:
    p=stdin_json(); token=optional_token(p.get("submission_token"))
    with store.lock():
        store.initialize(); tasks=store.load_tasks(); task=selected_task(store,tasks)
        if not task or task.status != "active": raise ManagerError("NO_TASK", "no active task is available", "Run 'manager status --compact'. If task is NO_TASK, run 'manager task add' with payload from schema_path, then run 'manager next'.")
        require_payload_agent_id(p, task)
        if token and token in store.load_submissions(): return store.remember_submission(token,p,store.load_submissions()[token].response)
        phase=task.phase
        if phase=="analysis":
            ensure_keys(p,{"agent_id","outcome","summary","finding_ids","decision_ids","atomic","decomposition_reason","blocker","evidence","recovery_condition","submission_token"},{"agent_id","outcome","summary","finding_ids","decision_ids","atomic"}); require_str(p["summary"],"summary")
            if p["outcome"]=="blocked":
                blocker=require_str(p.get("blocker"),"blocker"); evidence=require_list(p.get("evidence"),"evidence",True); recovery=require_str(p.get("recovery_condition"),"recovery_condition");
                transition_task(task, "blocked"); task.phase=None; task.blocker=blocker; task.updated=now(); store.save_task(task); append_evidence(store,task,"blocked",{"BLOCKER":blocker,"EVIDENCE":"\n".join(map(str,evidence)),"RECOVERY_CONDITION":recovery}); store.rebuild_index(); return store.remember_submission(token,p,"BLOCKED") if token else "BLOCKED"
            if p["outcome"]!="completed" or not isinstance(p["atomic"],bool): raise ManagerError("INVALID_SCHEMA","analysis outcome or atomic value is invalid","Submit completed with boolean atomic, or blocked with a blocker.")
            finding_ids = require_string_list(p["finding_ids"], "finding_ids")
            decision_ids = require_string_list(p["decision_ids"], "decision_ids")
            for rid in finding_ids + decision_ids:
                validate_refs_for_plan(task, store, [rid])
            if not p["atomic"]:
                reason=require_str(p.get("decomposition_reason"),"decomposition_reason"); transition_task(task, "expand"); task.phase=None; task.blocker=reason; task.updated=now(); store.save_task(task); store.rebuild_index(); return store.remember_submission(token,p,"OK DECOMPOSITION_REQUIRED") if token else "OK DECOMPOSITION_REQUIRED"
            task.phase="planning"; task.blocker=""; task.updated=now(); store.save_task(task); store.rebuild_index(); return store.remember_submission(token,p,"OK planning") if token else "OK planning"
        if phase=="planning":
            ensure_keys(p, {"agent_id", "steps", "final_validation", "submission_token"}, {"agent_id", "steps", "final_validation"})
            raw_steps = require_list(p["steps"], "steps", True)
            final_validation = require_string_list(p["final_validation"], "final_validation", True)
            existing = store.load_steps(task.id)
            if existing and not all(step.status in {"done", "failed", "blocked"} for step in existing):
                raise ManagerError("PLAN_EXISTS", f"task {task.id} already has an active plan", "Continue with the existing plan instead of replacing it.")
            titles: set[str] = set()
            actions: set[str] = set()
            normalized_steps = []
            for i, x in enumerate(raw_steps, 1):
                if not isinstance(x, dict):
                    raise ManagerError("INVALID_SCHEMA", "every step must be an object", "Resubmit a plan containing only step objects.")
                allowed = {"title", "action", "accept", "load", "may_edit", "validation", "commit_policy", "commit_type"}
                ensure_keys(x, allowed, allowed)
                title = require_str(x["title"], "step.title")
                action = require_str(x["action"], "step.action")
                if title.casefold() in titles:
                    raise ManagerError("INVALID_PLAN", f"duplicate step title at sequence {i}", "Each step must have a unique bounded action.")
                if len(title.split()) > 14 or len(action) > 500:
                    raise ManagerError("INVALID_PLAN", f"step {i} is not sufficiently bounded", "Split broad work into smaller child tasks or rewrite the action as one bounded outcome.")
                titles.add(title.casefold())
                action_key = " ".join(action.casefold().split())
                if action_key in actions:
                    raise ManagerError("INVALID_PLAN", f"duplicate normalized action at sequence {i}", "Each step must represent a distinct bounded action.")
                actions.add(action_key)
                accept = require_string_list(x["accept"], "step.accept", True)
                load = require_string_list(x["load"], "step.load")
                may_edit = require_string_list(x["may_edit"], "step.may_edit")
                validation = require_string_list(x["validation"], "step.validation", True)
                validation = [validate_command(v, "step.validation") for v in validation]
                if x["commit_policy"] not in {"required", "optional", "disabled"}:
                    raise ManagerError("INVALID_PLAN", "commit_policy must be required, optional, or disabled", "Use required, optional, or disabled.")
                if x["commit_type"] not in {"chore", "fix", "refactor", "test", "docs"}:
                    raise ManagerError("INVALID_PLAN", "unsupported commit_type", "Use chore, fix, refactor, test, or docs.")
                try:
                    for path in may_edit:
                        rel = rel_safe(str(path))
                        target = store.root / rel
                        resolved = target.resolve(strict=False)
                        if not resolved.is_relative_to(store.root.resolve()):
                            raise ValueError("edit boundary resolves outside repository")
                        if target.exists() and target.is_symlink():
                            raise ValueError("symlink edit boundaries are not permitted")
                except ValueError as exc:
                    raise ManagerError("INVALID_PLAN", str(exc), "Use repository-relative, non-symlink paths inside the application repository.")
                validate_refs_for_plan(task, store, list(map(str, load)))
                normalized_steps.append((title, action, accept, load, may_edit, validation, str(x["commit_policy"]), str(x["commit_type"])))
            if existing:
                archive_existing_steps(store, task.id, existing)
            first_step_number = store.next_step_number(task.id)
            for i, data in enumerate(normalized_steps, 1):
                title, action, accept, load, may_edit, validation, commit_policy, commit_type = data
                step_id = f"STEP-{first_step_number + i - 1:04d}"
                step_obj = Step(step_id, task.id, i, "ready" if i == 1 else "queued", PHASE_ROLE["implementation"], title, action, accept, load, may_edit, validation, commit_policy, commit_type, now(), now())
                store.save_step(step_obj)
            task.final_validation = [validate_command(v, "final_validation") for v in final_validation]
            task.current_step = f"STEP-{first_step_number:04d}"
            task.phase = "implementation"
            task.updated = now()
            store.save_task(task)
            store.rebuild_index()
            return store.remember_submission(token, p, f"OK {task.id} plan accepted") if token else f"OK {task.id} plan accepted"
        step=current_step(store,task)
        if phase=="implementation":
            if not step: raise ManagerError("CORRUPT_STATE","current implementation step is missing","Restore the canonical step record before continuing.")
            ensure_keys(p,{"agent_id","outcome","summary","changed_files","blocker","evidence","recovery_condition","submission_token"},{"agent_id","outcome","summary","changed_files"}); require_str(p["summary"],"summary"); reject_secret(p["summary"],"summary"); changed=require_string_list(p["changed_files"],"changed_files")
            if p["outcome"]=="blocked":
                blocker=require_str(p.get("blocker"),"blocker"); evidence=require_list(p.get("evidence"),"evidence",True); recovery=require_str(p.get("recovery_condition"),"recovery_condition"); transition_step(step, "blocked"); step.result=blocker; step.updated=now(); store.save_step(step); transition_task(task, "blocked"); task.phase=None; task.blocker=blocker; task.updated=now(); store.save_task(task); append_evidence(store,task,"blocked",{"STEP":step.id,"BLOCKER":blocker,"EVIDENCE":"\n".join(map(str,evidence)),"RECOVERY_CONDITION":recovery}); store.rebuild_index(); return store.remember_submission(token,p,"BLOCKED") if token else "BLOCKED"
            if p["outcome"]!="completed": raise ManagerError("INVALID_SCHEMA","implementation outcome must be completed or blocked","Submit a valid implementation result.")
            verify_changed_files(store,task,step,list(map(str,changed)))
            if step.status != "active":
                raise ManagerError("STEP_NOT_ACTIVE", f"step {step.id} is not active", "Run 'manager next' to activate the current ready step, then perform only its ACTION.")
            changed_for_evidence = enrich_file_evidence_list(store, changed, state="before", commit_id=git_head_commit(store)) if store.git_info()[0] else list(changed)
            transition_step(step, "implemented"); step.result=p["summary"]; transition_step(step, "validating"); step.updated=now(); store.save_step(step); task.phase="step_validation"; task.updated=now(); store.save_task(task); append_evidence(store,task,"implementation",{"STEP":step.id,"SUMMARY":p["summary"],"CHANGED_FILES":"\n".join(changed_for_evidence)}); store.rebuild_index(); return store.remember_submission(token,p,"OK step_validation") if token else "OK step_validation"
        if phase=="step_validation":
            if not step: raise ManagerError("CORRUPT_STATE","current validation step is missing","Restore the canonical step record before continuing.")
            ensure_keys(p,{"agent_id","outcome","runs","blocker","evidence","recovery_condition","submission_token"},{"agent_id","outcome","runs"}); runs=require_list(p["runs"],"runs",True)
            expected=step.validation
            seen=[]
            for r in runs:
                if not isinstance(r,dict): raise ManagerError("INVALID_SCHEMA","each validation run must be an object","Resubmit validation evidence using the returned schema.")
                ensure_keys(r,{"command","exit_code","summary"},{"command","exit_code","summary"}); command=validate_command(r["command"],"command"); summary=require_str(r["summary"],"summary"); reject_secret(summary,"summary");
                if command in seen: raise ManagerError("INVALID_SCHEMA", f"validation command was submitted more than once: {command}", "Submit exactly one result for each command listed in VALIDATION.")
                if not command_allowed(command,expected): raise ManagerError("UNAUTHORIZED_VALIDATION","validation command is not in the accepted plan: " + command,"Run only the exact validation commands listed in the current envelope.")
                if not isinstance(r["exit_code"], int) or isinstance(r["exit_code"], bool): raise ManagerError("INVALID_SCHEMA","exit_code must be an integer","Report the actual integer exit code.")
                seen.append(command)
            missing=[x for x in expected if x not in seen]
            if missing: raise ManagerError("INCOMPLETE_VALIDATION","required validation commands are missing: " + ", ".join(missing),"Run every command listed in VALIDATION and resubmit all results.")
            failed=[r for r in runs if r["exit_code"] != 0]
            if p["outcome"]=="passed" and failed: raise ManagerError("FALSE_PASS","validation was submitted as passed but a command exited non-zero","Submit failed with the actual exit codes.")
            if p["outcome"]=="failed" and not failed: raise ManagerError("FALSE_FAILURE","validation was submitted as failed but every command passed","Submit passed when every required command exited zero.")
            if p["outcome"]=="failed":
                transition_step(step, "failed"); step.result="Validation failed"; step.updated=now(); store.save_step(step); transition_step(step, "ready"); step.updated=now(); store.save_step(step); task.phase="implementation"; task.updated=now(); store.save_task(task); append_evidence(store,task,"validation",{"STEP":step.id,"RESULT":"failed","RUNS":json.dumps(runs),"COMMAND_ARGS":json.dumps({r["command"]: command_argv(r["command"]) for r in runs}, sort_keys=True)}); store.rebuild_index(); return store.remember_submission(token,p,"OK implementation") if token else "OK implementation"
            if p["outcome"]=="blocked":
                blocker=require_str(p.get("blocker"),"blocker"); evidence=require_list(p.get("evidence"),"evidence",True); recovery=require_str(p.get("recovery_condition"),"recovery_condition"); transition_step(step, "blocked"); step.result=blocker; store.save_step(step); transition_task(task, "blocked"); task.phase=None; task.blocker=blocker; task.updated=now(); store.save_task(task); append_evidence(store,task,"blocked",{"STEP":step.id,"BLOCKER":blocker,"EVIDENCE":"\n".join(map(str,evidence)),"RECOVERY_CONDITION":recovery}); store.rebuild_index(); return store.remember_submission(token,p,"BLOCKED") if token else "BLOCKED"
            if p["outcome"]!="passed": raise ManagerError("INVALID_SCHEMA","validation outcome must be passed, failed, or blocked","Submit the actual validation outcome.")
            transition_step(step, "validated"); step.validation_event=append_evidence(store,task,"validation",{"STEP":step.id,"RESULT":"passed","RUNS":json.dumps(runs),"COMMAND_ARGS":json.dumps({r["command"]: command_argv(r["command"]) for r in runs}, sort_keys=True)}); step.updated=now(); store.save_step(step); transition_step(step, "committing"); step.updated=now(); store.save_step(step); task.phase="step_commit"; task.updated=now(); store.save_task(task); store.rebuild_index(); return store.remember_submission(token,p,"OK step_commit") if token else "OK step_commit"
        if phase=="step_commit":
            recovered = recover_step_commit(store, task, step) if step else None
            if recovered:
                return recovered
            ensure_keys(p,{"agent_id","outcome","submission_token"},{"agent_id","outcome"})
            if p["outcome"] not in {"ready_to_commit", "skip_commit"}: raise ManagerError("INVALID_SCHEMA","step commit outcome must be ready_to_commit or skip_commit","Submit ready_to_commit for a manager-created commit, or skip_commit only when the step commit policy is optional.")
            if step.status not in {"validated", "committing"}: raise ManagerError("COMMIT_BEFORE_VALIDATION","step is not validated","Run the current validation phase and obtain a passed result before committing.")
            if p["outcome"] == "skip_commit":
                if step.commit_policy != "optional":
                    raise ManagerError("COMMIT_REQUIRED","this step does not permit skipping its commit gate","Submit ready_to_commit for a required/available manager commit, or use skip_commit only for an optional commit policy.")
                step.commit_id="skipped"; step.commit_message=""; transition_step(step, "done"); step.updated=now(); store.save_step(step); append_evidence(store,task,"commit_skipped",{"STEP":step.id,"COMMIT_POLICY":"optional"}); advance_after_step(store,task,step); return store.remember_submission(token,p,"OK implementation") if token else "OK implementation"
            if step.commit_policy=="disabled" or task.commit_mode=="disabled":
                step.commit_id="disabled"; transition_step(step, "done"); step.updated=now(); store.save_step(step); advance_after_step(store,task,step); return store.remember_submission(token,p,"OK implementation") if token else "OK implementation"
            paths=step.may_edit
            current=set(store.git_status_paths()); base=set(task.git_base); changed=sorted(current-base)
            if set(changed)-set(paths): raise ManagerError("DIRTY_WORKTREE","changes outside the current step boundary would be committed","Restore unrelated changes before requesting the manager commit.")
            if not changed: raise ManagerError("EMPTY_COMMIT","no application changes exist for the current required commit","Implement the step and report the actual changed files before requesting a commit.")
            message = f"{step.commit_type}: {step.title.lower()}"
            step.commit_message = message
            step.commit_base_head = store.git_head()
            transition_step(step, "committing")
            step.updated = now()
            store.save_step(step)
            store.refresh_integrity()
            cid = store.git_commit(paths, message)
            step.commit_id = cid
            transition_step(step, "done")
            step.updated = now()
            store.save_step(step)
            changed_after = enrich_file_evidence_list(store, store.git_commit_paths(cid), state="after", commit_id=cid)
            append_evidence(
                store,
                task,
                "commit",
                {
                    "STEP": step.id,
                    "COMMIT_TYPE": step.commit_type,
                    "COMMIT_ID": cid,
                    "MESSAGE": message,
                    "CHANGED_FILES_AFTER": "\n".join(changed_after),
                },
            )
            advance_after_step(store, task, step)
            return store.remember_submission(token, p, cid) if token else cid
        if phase=="final_validation":
            ensure_keys(p,{"agent_id","outcome","runs","review_findings","failure_classification","blocker","evidence","recovery_condition","diff_reviewed","submission_token"},{"agent_id","outcome","runs","review_findings","diff_reviewed"}); runs=require_list(p["runs"],"runs"); review=require_list(p["review_findings"],"review_findings")
            if p["diff_reviewed"] is not True: raise ManagerError("DIFF_REVIEW_REQUIRED","final validation must explicitly confirm the full diff was reviewed","Submit diff_reviewed: true after reviewing the complete relevant diff.")
            for finding in review:
                if not isinstance(finding, str) or not finding.strip(): raise ManagerError("INVALID_SCHEMA","review_findings must contain non-empty strings","Provide concise unresolved review findings as strings.")
            steps=store.load_steps(task.id); children=store.children(tasks,task.id)
            if children and not all(c.status=="done" for c in children): raise ManagerError("CHILDREN_INCOMPLETE","final validation is not allowed until all child tasks are done","Complete the remaining child task before final validation.")
            if steps and not all(s.status=="done" for s in steps): raise ManagerError("STEPS_INCOMPLETE","final validation is not allowed until all steps are done","Complete the remaining implementation steps before final validation.")
            for r in runs:
                if not isinstance(r,dict): raise ManagerError("INVALID_SCHEMA","each final validation run must be an object","Resubmit final validation evidence using the returned schema.")
                ensure_keys(r,{"command","exit_code","summary"},{"command","exit_code","summary"}); validate_command(r["command"],"command")
                if not isinstance(r["exit_code"], int) or isinstance(r["exit_code"], bool): raise ManagerError("INVALID_SCHEMA","exit_code must be an integer","Submit the actual integer process exit code.")
                summary=require_str(r["summary"],"summary"); reject_secret(summary,"summary")
                if r["command"] not in task.final_validation: raise ManagerError("UNAUTHORIZED_VALIDATION","final validation command is not in the accepted plan","Run only the exact final validation commands from the task plan.")
            missing=[x for x in task.final_validation if x not in [r["command"] for r in runs]]
            if missing: raise ManagerError("INCOMPLETE_VALIDATION","missing final validation commands: " + ", ".join(missing),"Run every final validation command and resubmit all results.")
            failed=[r for r in runs if r["exit_code"]!=0]
            if p["outcome"]=="passed" and (failed or review): raise ManagerError("FALSE_PASS","final validation cannot pass with failed commands or unresolved review findings","Submit failed and include the actual findings.")
            if p["outcome"]=="failed":
                classification = require_str(p.get("failure_classification"), "failure_classification")
                if classification not in {"implementation", "planning"}:
                    raise ManagerError("INVALID_SCHEMA", "failure_classification must be implementation or planning", "Classify the final failure as implementation or planning and resubmit.")
                append_evidence(store,task,"final_validation",{"RESULT":"failed","FAILURE_CLASSIFICATION":classification,"RUNS":json.dumps(runs),"COMMAND_ARGS":json.dumps({r["command"]: command_argv(r["command"]) for r in runs}, sort_keys=True),"REVIEW_FINDINGS":json.dumps(review)})
                if classification == "implementation" and len(review) == 1:
                    # Final review may return directly to implementation. Completed
                    # historical steps remain terminal; the manager creates one new
                    # corrective execution unit from the review finding, preserving
                    # the step FSM while satisfying the specified
                    # final_validation -> implementation path.
                    prior = steps[-1]
                    sequence = max((s.sequence for s in steps), default=0) + 1
                    # Step IDs are durable record identities, not positional sequence
                    # numbers. A final-review correction therefore allocates from the
                    # manager-wide per-task monotonic ID source so it cannot collide
                    # with archived steps from an earlier plan. The new correction
                    # starts in ready; only `manager next` may promote ready -> active.
                    step_number = store.next_step_number(task.id)
                    sid = f"STEP-{step_number:04d}"
                    correction = review[0].strip()
                    corrective = Step(
                        sid, task.id, sequence, "ready", PHASE_ROLE["implementation"],
                        "Correct final-review implementation defect", correction,
                        ["The final-review finding is resolved.", "The task remains within the approved application boundary."],
                        list(prior.load), sorted({path for s in steps for path in s.may_edit}),
                        list(prior.validation), prior.commit_policy, "fix", now(), now()
                    )
                    store.save_step(corrective)
                    task.current_step = sid
                    task.phase = "implementation"
                    task.updated = now()
                    store.save_task(task)
                    store.rebuild_index()
                    return store.remember_submission(token,p,"OK implementation") if token else "OK implementation"
                task.phase = "planning"
                task.current_step = None
                task.updated = now()
                store.save_task(task)
                store.rebuild_index()
                return store.remember_submission(token,p,"OK planning") if token else "OK planning"
            if p["outcome"]=="blocked":
                blocker=require_str(p.get("blocker"),"blocker"); evidence=require_list(p.get("evidence"),"evidence",True); recovery=require_str(p.get("recovery_condition"),"recovery_condition"); transition_task(task, "blocked"); task.phase=None; task.blocker=blocker; task.updated=now(); store.save_task(task); append_evidence(store,task,"blocked",{"BLOCKER":blocker,"EVIDENCE":"\n".join(map(str,evidence)),"RECOVERY_CONDITION":recovery}); store.rebuild_index(); return store.remember_submission(token,p,"BLOCKED") if token else "BLOCKED"
            if p["outcome"]!="passed": raise ManagerError("INVALID_SCHEMA","final validation outcome must be passed, failed, or blocked","Submit the actual final validation outcome.")
            append_evidence(store,task,"final_validation",{"RESULT":"passed","RUNS":json.dumps(runs),"COMMAND_ARGS":json.dumps({r["command"]: command_argv(r["command"]) for r in runs}, sort_keys=True),"REVIEW_FINDINGS":"none"}); task.phase="final_commit"; task.updated=now(); store.save_task(task); store.rebuild_index(); return store.remember_submission(token,p,"OK final_commit") if token else "OK final_commit"
        if phase=="final_commit":
            recovered = recover_final_commit(store, task)
            if recovered:
                return recovered
            ensure_keys(p,{"agent_id","outcome","submission_token"},{"agent_id","outcome"})
            if p["outcome"]!="ready_to_commit": raise ManagerError("INVALID_SCHEMA","final commit outcome must be ready_to_commit","Submit the exact final commit readiness result.")
            steps=store.load_steps(task.id)
            if not all(s.status=="done" for s in steps): raise ManagerError("COMMIT_GATE","final commit requires all steps done","Complete every implementation step before final commit.")
            if task.commit_mode=="disabled":
                transition_task(task, "done"); task.phase=None; task.current_step=None; task.updated=now(); store.save_task(task); store.rebuild_index(); return store.remember_submission(token,p,"OK done") if token else "OK done"
            current=set(store.git_status_paths()); base=set(task.git_base); changed=sorted(current-base)
            # Final integration commits may contain only paths explicitly authorized by
            # implementation steps. This prevents unrelated post-step edits from being
            # silently swept into the feature commit.
            if any(p==".manager" or p.startswith(".manager/") for p in changed):
                raise ManagerError("MANAGED_FILE_CHANGE","final commit would include manager-owned files","Do not include .manager files in application commits.")
            allowed={path for s in steps for path in s.may_edit}
            unauthorized=sorted(set(changed)-allowed)
            if unauthorized:
                raise ManagerError("DIRTY_WORKTREE","changes outside the task's approved final boundary would be committed: " + ", ".join(unauthorized),"Restore unrelated changes before requesting the final commit.")
            message = f"feat: {task.title.lower()}"
            task.final_commit_message = message
            task.updated = now()
            task.git_base_head = store.git_head()
            store.save_task(task)
            store.refresh_integrity()
            cid = store.git_commit(changed, message, allow_empty=True)
            task.final_commit_id = cid
            changed_after = enrich_file_evidence_list(store, store.git_commit_paths(cid), state="after", commit_id=cid)
            append_evidence(
                store,
                task,
                "commit",
                {
                    "STEP": "FINAL",
                    "COMMIT_TYPE": "feat",
                    "COMMIT_ID": cid,
                    "MESSAGE": message,
                    "CHANGED_FILES_AFTER": "\n".join(changed_after),
                },
            )
            transition_task(task, "done")
            task.phase = None
            task.current_step = None
            task.updated = now()
            store.save_task(task)
            store.rebuild_index()
            return store.remember_submission(token, p, cid) if token else cid
        raise ManagerError("INVALID_PHASE","current task has no supported execution phase","Run 'manager next' to reconstruct the current execution envelope.")


def advance_after_step(store: Store, task: Task, step: Step) -> None:
    steps=store.load_steps(task.id)
    nxt=next((s for s in steps if s.sequence > step.sequence and s.status=="queued"),None)
    if nxt:
        transition_step(nxt, "ready"); nxt.updated=now(); store.save_step(nxt); task.current_step=nxt.id; task.phase="implementation"; task.updated=now(); store.save_task(task)
    else:
        task.current_step=None; task.phase="final_validation"; task.updated=now(); store.save_task(task)
    store.rebuild_index()


def cmd_decision_resolve(store: Store) -> str:
    p = stdin_json()
    ensure_keys(p, {"task", "agent_id", "decision_id", "status", "submission_token"}, {"agent_id", "decision_id", "status"})
    if p["status"] not in {"accepted", "rejected"}:
        raise ManagerError("INVALID_SCHEMA", "decision status must be accepted or rejected", "Choose accepted or rejected.")
    with store.lock():
        store.initialize(); tasks = store.load_tasks(); task = tasks.get(p.get("task")) if p.get("task") else selected_task(store, tasks)
        if not task or task.phase != "analysis":
            raise ManagerError("INVALID_PHASE", "decisions can only be resolved during analysis", "Run 'manager next' and follow the analysis phase.")
        require_payload_agent_id(p, task)
        did = require_str(p["decision_id"], "decision_id")
        path = store.knowledge_dir / f"{task.id}-decisions.md"
        if not path.exists():
            raise ManagerError("MISSING_DECISION", f"decision {did} does not exist", "Use an existing proposed decision ID.")
        text = path.read_text(encoding="utf-8")
        marker = f"## {did}"
        if marker not in text:
            raise ManagerError("MISSING_DECISION", f"decision {did} does not exist", "Use an existing proposed decision ID.")
        chunk = text.split(marker, 1)[1].split("\n## ", 1)[0]
        resolutions = re.findall(r"## DECISION-RESOLUTION-" + re.escape(did) + r"\n\nDECISION_ID:\n" + re.escape(did) + r"\n\nSTATUS:\n([^\n]+)", text)
        if resolutions:
            return f"OK {did} already {resolutions[-1].strip()}"
        if "STATUS:\nproposed" not in chunk:
            raise ManagerError("INVALID_DECISION", f"decision {did} is not in proposed state", "Resolve only a proposed decision.")
        # Decisions are append-only: retain the original proposal and append a resolution event.
        resolution = f"\n\n## DECISION-RESOLUTION-{did}\n\nDECISION_ID:\n{did}\n\nSTATUS:\n{p['status']}\n\nRECORDED_AT:\n{now()}\n"
        fm, body = __import__("manager.core", fromlist=["parse_frontmatter"]).parse_frontmatter(text)
        fm["updated"] = now()
        updated_body = body.rstrip() + resolution

        # If this newly accepted decision supersedes an earlier accepted
        # decision, append the supersession event now. The proposal itself
        # never mutates the lifecycle of the earlier decision.
        if p["status"] == "accepted":
            supersedes_match = re.search(
                r"^SUPERSEDES:\n([^\n]+)",
                chunk,
                flags=re.MULTILINE,
            )
            supersedes = supersedes_match.group(1).strip() if supersedes_match else "None"
            if supersedes and supersedes != "None":
                old_marker = f"## {supersedes}"
                if old_marker not in updated_body:
                    raise ManagerError("MISSING_DECISION", f"superseded decision {supersedes} does not exist", "Restore the referenced decision before accepting this proposal.")
                old_resolutions = re.findall(
                    r"## DECISION-RESOLUTION-" + re.escape(supersedes) +
                    r"\n\nDECISION_ID:\n" + re.escape(supersedes) +
                    r"\n\nSTATUS:\n([^\n]+)",
                    updated_body,
                )
                if not old_resolutions or old_resolutions[-1].strip() != "accepted":
                    raise ManagerError("INVALID_DECISION", f"decision {supersedes} is not accepted", "Only an accepted decision may be superseded.")
                updated_body += (
                    f"\n\n## DECISION-RESOLUTION-{supersedes}"
                    f"\n\nDECISION_ID:\n{supersedes}"
                    f"\n\nSTATUS:\nsuperseded"
                    f"\n\nSUPERSEDED_BY:\n{did}"
                    f"\n\nRECORDED_AT:\n{now()}\n"
                )
        store.save_record(path, fm, updated_body)
        return f"OK {did} {p['status']}"


def blocked_recovery_condition(store: Store, task: Task) -> str:
    if not task.evidence:
        return "unknown"
    path = store.evidence_dir / f"{task.id}-evidence.md"
    if not path.exists():
        return "unknown"
    _, body = __import__("manager.core", fromlist=["parse_frontmatter"]).parse_frontmatter(path.read_text(encoding="utf-8"))
    matches = re.findall(r"## EVT-\d{4}\n\nTYPE:\nblocked\n\nRECORDED_AT:\n[^\n]+\n(.*?)(?=\n## EVT-|\Z)", body, flags=re.DOTALL)
    if not matches:
        return "unknown"
    latest = matches[-1]
    found = re.search(r"\nRECOVERY_CONDITION:\n(.*?)(?=\n[A-Z_]+:\n|\Z)", "\n" + latest, flags=re.DOTALL)
    return found.group(1).strip() if found and found.group(1).strip() else "unknown"


def cmd_submit_schema(store: Store, as_json: bool = False, path_only: bool = False) -> str:
    with store.lock():
        store.initialize()
        tasks = store.load_tasks()
        task = selected_task(store, tasks)
        if not task or task.status != "active":
            raise ManagerError("NO_TASK", "no active task is available", "Run 'manager status --compact'. If task is NO_TASK, run 'manager task add' with payload from schema_path, then run 'manager next'.")
        payload = next_envelope_payload(store, task, promote_ready=False)
        if not payload:
            raise ManagerError("INVALID_PHASE", "no active phase schema is available", "Run 'manager next' to reconstruct the current phase.")
        schema_path = persist_return_schema(store, payload["return_schema"])
        if path_only:
            if as_json:
                return json.dumps({"schema_path": schema_path}, indent=2)
            return schema_path + "\n"
        if as_json:
            return json.dumps({
                "task": payload["task"],
                "phase": payload["phase"],
                "return_schema": payload["return_schema"],
                "return_schema_path": schema_path,
                "output_limit": payload["output_limit"],
                "submit_command": payload["submit_command"],
                "recommended_context_command": payload["recommended_context_command"],
                "micro_cycle": payload["micro_cycle"],
            }, indent=2)
        return "\n".join([
            f"TASK: {payload['task']}",
            f"PHASE: {payload['phase']}",
            "RETURN_SCHEMA:",
            json.dumps(payload["return_schema"], indent=2),
            "",
            "RETURN_SCHEMA_PATH:",
            schema_path,
            "",
            "OUTPUT_LIMIT:",
            f"{payload['output_limit']} characters per textual result field",
            "",
            "SUBMIT_COMMAND:",
            payload["submit_command"],
            "",
            "RECOMMENDED_CONTEXT_COMMAND:",
            payload["recommended_context_command"],
        ]) + "\n"


def cmd_bootstrap(store: Store, as_json: bool = False) -> str:
    with store.lock():
        store.initialize()
        tasks = store.load_tasks()
        task = selected_task(store, tasks)
        step = current_step(store, task) if task and task.status == "active" else None
        role = PHASE_ROLE.get(task.phase) if task and task.phase else None
        status_payload = {
            "ok": True,
            "task": task.id if task else "NO_TASK",
            "phase": task.phase if task and task.phase else "none",
            "step": step.id if step else "none",
            "role": role if role else "none",
        }
        payload = {
            "protocol": "manager-low-context-v1",
            "prompt": PROMPT.strip(),
            "startup_commands": [
                "manager next",
                f"manager context --compact --max-chars {DEFAULT_CONTEXT_MAX_CHARS}",
                "manager submit-schema",
                "manager submit",
                "manager status --compact",
                "manager verify",
            ],
            "micro_cycle": MICRO_CYCLE,
            "error_contract": ["error", "what", "do", "hint?", "gotcha?"],
            "status": status_payload,
        }
        if as_json:
            return json.dumps(payload, indent=2)
        return "\n".join(
            [
                "BOOTSTRAP:",
                json.dumps(payload, indent=2),
            ]
        ) + "\n"


def cmd_verify(store: Store, as_json: bool = False) -> str:
    if not store.meta.exists():
        result = {"ok": True, "state": "NO_STATE"}
        return json.dumps(result, indent=2) if as_json else "OK NO_STATE\n"
    store.validate()
    tasks = store.load_tasks()
    task = selected_task(store, tasks)
    result = {
        "ok": True,
        "format_version": FORMAT_VERSION,
        "total_tasks": len(tasks),
        "current": task.id if task else "NO_TASK",
    }
    return json.dumps(result, indent=2) if as_json else f"OK CURRENT={result['current']} TOTAL={result['total_tasks']}\n"


def cmd_examples(as_json: bool = False) -> str:
    sample_agent_id = "00000000-0000-4000-8000-000000000001"
    examples = {
        "analysis": {"agent_id": sample_agent_id, "outcome": "completed", "summary": "done", "finding_ids": [], "decision_ids": [], "atomic": True},
        "planning": {"agent_id": sample_agent_id, "steps": [{"title": "Implement", "action": "Implement", "accept": ["works"], "load": [], "may_edit": ["app.py"], "validation": ["python -m unittest"], "commit_policy": "disabled", "commit_type": "chore"}], "final_validation": ["python -m unittest"]},
        "implementation": {"agent_id": sample_agent_id, "outcome": "completed", "summary": "implemented", "changed_files": ["app.py"]},
        "step_validation": {"agent_id": sample_agent_id, "outcome": "passed", "runs": [{"command": "python -m unittest", "exit_code": 0, "summary": "ok"}]},
        "step_commit": {"agent_id": sample_agent_id, "outcome": "ready_to_commit"},
        "final_validation": {"agent_id": sample_agent_id, "outcome": "passed", "runs": [], "review_findings": [], "diff_reviewed": True},
        "final_commit": {"agent_id": sample_agent_id, "outcome": "ready_to_commit"},
    }
    if as_json:
        return json.dumps({"examples": examples}, indent=2)
    lines = ["EXAMPLES:"]
    for phase, value in examples.items():
        lines += ["", f"PHASE: {phase}", json.dumps(value, indent=2)]
    return "\n".join(lines) + "\n"


def next_learning_id(path: Path) -> str:
    if not path.exists():
        return "LEARN-0001"
    text = path.read_text(encoding="utf-8")
    nums = [int(x) for x in re.findall(r"^## LEARN-(\d{4})$", text, flags=re.MULTILINE)]
    return f"LEARN-{max(nums, default=0) + 1:04d}"


def cmd_learn_add(store: Store) -> dict[str, Any]:
    p = stdin_json()
    ensure_keys(p, {"issue", "error_code", "phase", "suggestion", "impact", "evidence", "severity", "submission_token"}, {"issue"})
    issue = require_str(p["issue"], "issue")
    error_code = require_str(p.get("error_code"), "error_code") if p.get("error_code") is not None else ""
    phase = require_str(p.get("phase"), "phase") if p.get("phase") is not None else ""
    suggestion = require_str(p.get("suggestion"), "suggestion") if p.get("suggestion") is not None else ""
    impact = require_str(p.get("impact"), "impact") if p.get("impact") is not None else ""
    severity = require_str(p.get("severity"), "severity") if p.get("severity") is not None else "medium"
    if severity not in {"low", "medium", "high"}:
        raise ManagerError("INVALID_SCHEMA", "severity must be low, medium, or high", "Provide severity as one of: low, medium, high.")
    evidence = require_string_list(p.get("evidence", []), "evidence")
    token = optional_token(p.get("submission_token"))

    with store.lock():
        store.initialize()
        if token:
            existing = store.load_submissions().get(token)
            if existing:
                try:
                    return json.loads(existing.response)
                except json.JSONDecodeError:
                    return {"result": existing.response}
        tasks = store.load_tasks()
        task = selected_task(store, tasks)
        path = store.meta / "learning.md"
        rid = next_learning_id(path)
        fm = {
            "type": "learning",
            "format_version": FORMAT_VERSION,
            "id": "MANAGER-LEARNING",
            "created": now(),
            "updated": now(),
        }
        section_lines = [
            f"## {rid}",
            "",
            "RECORDED_AT:",
            now(),
            "",
            "TASK:",
            task.id if task else "NO_TASK",
            "",
            "PHASE:",
            phase or (task.phase if task and task.phase else "none"),
            "",
            "SEVERITY:",
            severity,
            "",
            "ISSUE:",
            issue,
            "",
            "ERROR_CODE:",
            error_code or "none",
            "",
            "IMPACT:",
            impact or "none",
            "",
            "SUGGESTION:",
            suggestion or "none",
            "",
            "EVIDENCE:",
        ]
        if evidence:
            section_lines.extend(f"- {item}" for item in evidence)
        else:
            section_lines.append("- none")
        section = "\n".join(section_lines) + "\n"
        if not path.exists():
            store.append_record(path, fm, "# Manager Learning Log\n\n" + section)
        else:
            fm_existing, _ = __import__("manager.core", fromlist=["parse_frontmatter"]).parse_frontmatter(path.read_text(encoding="utf-8"))
            fm_existing["updated"] = now()
            store.append_record(path, fm_existing, section)
        result = {
            "id": rid,
            "recorded_at": now(),
            "task": task.id if task else "NO_TASK",
            "phase": phase or (task.phase if task and task.phase else "none"),
            "severity": severity,
        }
        if token:
            store.remember_submission(token, p, json.dumps(result, separators=(",", ":")))
        return result


def cmd_learn_list(store: Store, limit: int = 20) -> dict[str, Any]:
    if limit <= 0 or limit > 500:
        raise ManagerError("INVALID_SCHEMA", "limit must be between 1 and 500", "Provide a limit value from 1 through 500.")
    with store.lock():
        store.initialize()
        path = store.meta / "learning.md"
        if not path.exists():
            return {"records": []}
        _, body = __import__("manager.core", fromlist=["parse_frontmatter"]).parse_frontmatter(path.read_text(encoding="utf-8"))
        chunks = re.findall(r"## LEARN-\d{4}\n(.*?)(?=\n## LEARN-|\Z)", body, flags=re.DOTALL)
        ids = re.findall(r"^## (LEARN-\d{4})$", body, flags=re.MULTILINE)
        records: list[dict[str, Any]] = []
        for rid, chunk in zip(ids, chunks):
            def field(name: str, default: str = "") -> str:
                m = re.search(r"^" + re.escape(name) + r":\n(.*?)(?=\n[A-Z_]+:\n|\Z)", chunk, flags=re.MULTILINE | re.DOTALL)
                return m.group(1).strip() if m else default
            evidence = [x[2:].strip() for x in field("EVIDENCE", "").splitlines() if x.startswith("- ")]
            records.append(
                {
                    "id": rid,
                    "recorded_at": field("RECORDED_AT"),
                    "task": field("TASK", "NO_TASK"),
                    "phase": field("PHASE", "none"),
                    "severity": field("SEVERITY", "medium"),
                    "issue": field("ISSUE"),
                    "error_code": field("ERROR_CODE", "none"),
                    "impact": field("IMPACT", "none"),
                    "suggestion": field("SUGGESTION", "none"),
                    "evidence": evidence,
                }
            )
        return {"records": records[-limit:]}



def cmd_learn_from_log(store: Store, limit: int = 50, create_tasks: bool = False) -> dict[str, Any]:
    if limit <= 0 or limit > 500:
        raise ManagerError("INVALID_SCHEMA", "limit must be between 1 and 500", "Provide a limit value from 1 through 500.")

    with store.lock():
        store.initialize()
        runtime_dir = store.meta / RUNTIME_DIR
        paths = sorted(runtime_dir.glob("error-*-log.ndjson")) if runtime_dir.exists() else []
        if not paths:
            legacy = runtime_path(store, ERROR_LOG_FILE)
            if legacy.exists():
                paths = [legacy]
        if not paths:
            return {"records": [], "rcas": [], "created_tasks": [], "reminder": ASD_STE100_REMINDER}

        parsed_entries: list[dict[str, Any]] = []
        raw_records: list[str] = []
        for path in paths:
            inferred_agent_id = sanitize_agent_id(generated_agent_id("learn-from-log"))
            if path.name.startswith("error-") and path.name.endswith("-log.ndjson"):
                inferred_agent_id = path.name[len("error-") : -len("-log.ndjson")] or inferred_agent_id
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                raw_records.append(line)
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                if not str(entry.get("agent_id", "")).strip():
                    entry["agent_id"] = inferred_agent_id
                parsed_entries.append(entry)

        parsed_entries.sort(key=lambda item: str(item.get("recorded_at", "")))
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in parsed_entries[-limit:]:
            output = entry.get("output")
            if not isinstance(output, dict) or not output.get("error"):
                continue
            error_code = str(output.get("error", "UNKNOWN")).strip() or "UNKNOWN"
            what = str(output.get("what", "unspecified failure")).strip() or "unspecified failure"
            key = (error_code, what)
            bucket = grouped.setdefault(
                key,
                {
                    "error": error_code,
                    "what": what,
                    "count": 0,
                    "first_seen": entry.get("recorded_at", ""),
                    "last_seen": entry.get("recorded_at", ""),
                    "commands": set(),
                    "do": str(output.get("do", "")).strip(),
                },
            )
            bucket["count"] += 1
            bucket["last_seen"] = entry.get("recorded_at", bucket["last_seen"])
            command = str(entry.get("command", "")).strip()
            if command:
                bucket["commands"].add(command)

        ranked = sorted(grouped.values(), key=lambda x: (-int(x["count"]), str(x["error"]), str(x["what"])))
        rcas: list[dict[str, Any]] = []
        for index, item in enumerate(ranked, 1):
            command_list = sorted(item["commands"])
            rcas.append(
                {
                    "id": f"RCA-{index:04d}",
                    "error": item["error"],
                    "what": item["what"],
                    "count": item["count"],
                    "first_seen": item["first_seen"],
                    "last_seen": item["last_seen"],
                    "commands": command_list,
                    "suggested_fix": item["do"] or "Use manager context and schema output to submit the exact required payload.",
                }
            )

        created_tasks: list[dict[str, str]] = []
        if create_tasks and rcas:
            tasks = store.load_tasks()
            normalized_titles = {" ".join(task.title.casefold().split()) for task in tasks.values() if task.status != "done"}
            for rca in rcas:
                title = f"Fix manager {rca['error'].lower().replace('_', ' ')}"
                normalized = " ".join(title.casefold().split())
                if normalized in normalized_titles:
                    continue
                tid = store.allocate_task_id(tasks, parent=None, new_story=True)
                what = (
                    f"Fix root cause {rca['error']} from .manager/runtime/{ERROR_LOG_FILE_TEMPLATE}. "
                    "Deliver one atomic fix for this RCA."
                )
                done_when = "A single focused fix is validated and ready for one commit."
                why = f"Error '{rca['what']}' occurred {rca['count']} time(s)."
                how = "Investigate the failing command flow and apply one code fix for this RCA only."
                constraints = [
                    "One fix per commit.",
                    "Do not combine unrelated RCA fixes in the same commit.",
                ]
                task = Task(
                    store.tasks_dir / "placeholder.md",
                    tid,
                    title,
                    None,
                    task_sequence_for_id(tid),
                    3,
                    "planned",
                    None,
                    None,
                    store.commit_mode(),
                    "",
                    now(),
                    now(),
                    agent_id=generated_agent_id(tid),
                    body=task_body(title, what, done_when, why, how, constraints),
                )
                store.save_task(task)
                tasks[task.id] = task
                normalized_titles.add(normalized)
                created_tasks.append({"id": tid, "title": title})
            if created_tasks:
                store.rebuild_index()

        return {
            "records": raw_records[-limit:],
            "rcas": rcas,
            "created_tasks": created_tasks,
            "reminder": ASD_STE100_REMINDER,
        }
def cmd_status(store: Store, compact: bool = False, as_json: bool = False) -> str:
    with store.lock():
        store.initialize(); tasks=store.load_tasks(); counts={s:0 for s in TASK_STATES};
        for t in tasks.values(): counts[t.status]+=1
        task=selected_task(store,tasks)
        step = current_step(store, task) if task and task.status == "active" else None
        role = PHASE_ROLE.get(task.phase) if task and task.phase else None
        blocked = next((t for t in sorted(tasks.values(), key=lambda x: x.order_key) if t.status == "blocked"), None)
        blocked_payload = None
        if blocked:
            blocked_payload = {
                "task": blocked.id,
                "blocker": blocked.blocker or "unknown",
                "recovery": blocked_recovery_condition(store, blocked),
                "action": f"manager unblock {blocked.id}",
            }
        payload = {
            "format_version": FORMAT_VERSION,
            "root": str(store.root),
            "commit_mode": store.commit_mode(),
            "total": len(tasks),
            "states": counts,
            "current": {
                "task": task.id if task else "NO_TASK",
                "phase": task.phase if task and task.phase else "none",
                "step": step.id if step else "none",
                "role": role if role else "none",
            },
            "blocked": blocked_payload,
        }
        if compact:
            compact_payload = {
                "ok": True,
                "task": payload["current"]["task"],
                "phase": payload["current"]["phase"],
                "step": payload["current"]["step"],
                "role": payload["current"]["role"],
            }
            if as_json:
                return json.dumps(compact_payload, indent=2)
            return f"OK TASK={compact_payload['task']} PHASE={compact_payload['phase']} STEP={compact_payload['step']} ROLE={compact_payload['role']}\n"
        if as_json:
            return json.dumps(payload, indent=2)
        lines=[f"MANAGER FORMAT: {FORMAT_VERSION}",f"ROOT: {store.root}",f"COMMIT_MODE: {store.commit_mode()}",f"TOTAL: {len(tasks)}", "STATES: "+" ".join(f"{k}={counts[k]}" for k in sorted(counts))]
        lines.append(f"CURRENT: {task.id if task else 'NO_TASK'}")
        if blocked_payload:
            lines += [
                f"BLOCKED: {blocked_payload['task']}",
                f"BLOCKER: {blocked_payload['blocker']}",
                f"RECOVERY: {blocked_payload['recovery']}",
                f"ACTION: {blocked_payload['action']}",
            ]
        return "\n".join(lines)+"\n"


def cmd_prompt(_: argparse.Namespace) -> str: return PROMPT


def build_parser() -> argparse.ArgumentParser:
    p=ManagerArgumentParser(
        description="Deterministic filesystem-backed agent work orchestrator",
        epilog=(
            "Discovery: use 'manager task --help', 'manager decision --help', "
            "'manager learn --help', and 'manager plan --help'.\n"
            "Stdin commands require piped/heredoc input and time out after "
            f"{STDIN_READ_TIMEOUT_SECONDS}s if no payload is received."
        ),
    )
    p.add_argument("--root", default=".", help="workspace root")
    p.add_argument("--json", action="store_true", help="deprecated: JSON is now the default output format")
    p.add_argument("--prompt", action="store_true")
    sub=p.add_subparsers(dest="command")
    for name, helptext in [("next","return one execution envelope"),("submit","submit phase result"),("status","show manager status")]:
        sub.add_parser(name,help=helptext)
    ss=sub.add_parser("submit-schema", help="return only the currently accepted submit schema")
    ss.add_argument("--schema-path", action="store_true", help="return only the direct path to the active RETURN_SCHEMA file")
    sub.add_parser("bootstrap", help="return low-context startup protocol, commands, and compact status")
    sub.add_parser("verify", help="run manager consistency checks without mutating managed state")
    sub.add_parser("examples", help="show minimal phase submission examples")
    c=sub.add_parser("context", help="resolve current context"); c.add_argument("ref",nargs="?"); c.add_argument("--compact", action="store_true", help="return a bounded summary projection"); c.add_argument("--max-chars", type=int, default=DEFAULT_CONTEXT_MAX_CHARS, help="max characters for each projected context block")
    sub.choices["status"].add_argument("--compact", action="store_true", help="emit a single machine-friendly summary line")
    c=sub.add_parser("block"); c.add_argument("task",nargs="?")
    c=sub.add_parser("unblock"); c.add_argument("task",nargs="?")
    task=sub.add_parser("task"); ts=task.add_subparsers(dest="task_command")
    a=ts.add_parser("add"); a.add_argument("--new-story",action="store_true")
    pl=ts.add_parser("plan"); pl.add_argument("task",nargs="?")
    ed=ts.add_parser("edit"); ed.add_argument("task",nargs="?")
    ex=ts.add_parser("expand"); ex.add_argument("task",nargs="?")
    f=sub.add_parser("finding"); fs=f.add_subparsers(dest="finding_command"); fs.add_parser("add")
    e=sub.add_parser("evidence"); es=e.add_subparsers(dest="evidence_command"); es.add_parser("add")
    d=sub.add_parser("decision"); ds=d.add_subparsers(dest="decision_command"); ds.add_parser("propose"); dr=ds.add_parser("resolve")
    l=sub.add_parser("learn", help="record and list manual manager improvement issues")
    ls=l.add_subparsers(dest="learn_command")
    ls.add_parser("add", help="append one learning record from stdin JSON")
    ll=ls.add_parser("list", help="list learning records")
    ll.add_argument("--limit", type=int, default=20)
    lf = ls.add_parser("from-log", help="analyze .manager/runtime/error-<agent-id>-log.ndjson files for RCAs")
    lf.add_argument("--limit", type=int, default=50)
    lf.add_argument("--create-tasks", action="store_true", help="create one planned story/task per RCA with one-fix-per-commit constraints")
    ps=sub.add_parser("plan"); pss=ps.add_subparsers(dest="plan_command"); pss.add_parser("submit")
    return p


def main() -> None:
    parser=build_parser()
    fallback_store = Store(Path("."))
    if len(sys.argv)==1:
        msg = ManagerError("NO_COMMAND", "no command provided", "Run 'manager --prompt' for the operating protocol.")
        print(render_manager_error(msg, fallback_store, as_json=True), file=sys.stderr)
        raise SystemExit(2)
    try:
        args=parser.parse_args()
    except ManagerError as exc:
        print(render_manager_error(exc, fallback_store, as_json=True), file=sys.stderr)
        raise SystemExit(2)
    if args.prompt: print(PROMPT,end=""); return
    stdin_payload = ""
    reads_stdin = (
        args.command == "submit"
        or args.command == "block"
        or (args.command == "task" and args.task_command in {"add", "edit"})
        or (args.command == "finding" and args.finding_command == "add")
        or (args.command == "evidence" and args.evidence_command == "add")
        or (args.command == "decision" and args.decision_command in {"propose", "resolve"})
        or (args.command == "learn" and args.learn_command == "add")
        or (args.command == "plan" and args.plan_command == "submit")
    )
    store=Store(Path(args.root))
    output_json = True
    mutating = False
    try:
        if reads_stdin:
            command_label = "manager " + " ".join(sys.argv[1:]).strip()
            stdin_payload = read_stdin_with_timeout(sys.stdin, STDIN_READ_TIMEOUT_SECONDS, command_label)
            sys.stdin = io.StringIO(stdin_payload)
        if args.command=="next": out=cmd_next(store, as_json=True); mutating=True
        elif args.command=="context": out=cmd_context(store,args.ref,args.compact,args.max_chars,as_json=True)
        elif args.command=="submit": out=cmd_submit(store); mutating=True
        elif args.command=="submit-schema": out=cmd_submit_schema(store, as_json=True, path_only=getattr(args, "schema_path", False))
        elif args.command=="bootstrap": out=cmd_bootstrap(store, as_json=True)
        elif args.command=="verify": out=cmd_verify(store, as_json=True)
        elif args.command=="examples": out=cmd_examples(as_json=True)
        elif args.command=="status": out=cmd_status(store, compact=getattr(args, "compact", False), as_json=True)
        elif args.command=="block": out=cmd_task_block(store,args.task); mutating=True
        elif args.command=="unblock": out=cmd_task_unblock(store,args.task); mutating=True
        elif args.command=="task" and args.task_command=="add": out=cmd_task_add(store,args); mutating=True
        elif args.command=="task" and args.task_command=="plan": out=cmd_plan_task(store,args.task); mutating=True
        elif args.command=="task" and args.task_command=="edit": out=cmd_task_edit(store,args.task); mutating=True
        elif args.command=="task" and args.task_command=="expand": out=cmd_task_expand(store,args.task); mutating=True
        elif args.command=="finding" and args.finding_command=="add": out=cmd_finding_add(store); mutating=True
        elif args.command=="evidence" and args.evidence_command=="add": out=cmd_evidence_add(store); mutating=True
        elif args.command=="plan" and args.plan_command=="submit":
            store.initialize()
            tasks=store.load_tasks(); task=selected_task(store,tasks)
            if not task or task.status != "active" or task.phase != "planning":
                raise ManagerError("INVALID_PHASE", "plan submission is only valid during planning", "Run 'manager next' and follow the planner envelope.")
            out=cmd_plan_submit(store, task, stdin_json()); mutating=True
        elif args.command=="decision" and args.decision_command=="propose": out=cmd_decision_propose(store); mutating=True
        elif args.command=="decision" and args.decision_command=="resolve": out=cmd_decision_resolve(store); mutating=True
        elif args.command == "learn" and args.learn_command == "add":
            out = cmd_learn_add(store)
            mutating = True
        elif args.command == "learn" and args.learn_command == "list":
            out = cmd_learn_list(store, args.limit)
        elif args.command == "learn" and args.learn_command == "from-log":
            out = cmd_learn_from_log(store, limit=args.limit, create_tasks=getattr(args, "create_tasks", False))
            mutating = bool(getattr(args, "create_tasks", False))
        else:
            raise ManagerError(
                "INVALID_COMMAND",
                "unsupported or incomplete command",
                "Run 'manager --prompt' to view the command protocol and valid command sequence.",
            )
        if mutating:
            # The integrity manifest is itself manager-owned state; its mutation must
            # occur under the same exclusive workspace lock as every other mutation.
            with store.lock():
                store.refresh_integrity()
        rendered = emit_output(out, as_json=output_json)
        print(rendered,end="" if rendered.endswith("\n") else "\n")
        record_command_outcome(store, sys.argv[1:], stdin_payload, rendered, success=True, command_name=args.command)
    except ManagerError as exc:
        schema_path = None
        if exc.code == "INVALID_SCHEMA":
            if args.command == "task" and args.task_command == "add":
                schema_path = resolve_task_add_schema_path(store)
            else:
                schema_path = resolve_active_return_schema_path(store)
        elif exc.code == "NO_TASK":
            schema_path = resolve_task_add_schema_path(store)
        rendered_error = render_manager_error(exc, store, as_json=output_json, schema_path=schema_path)
        print(rendered_error,file=sys.stderr)
        record_command_outcome(store, sys.argv[1:], stdin_payload, rendered_error, success=False, command_name=args.command)
        raise SystemExit(2)
    except (OSError, ValueError) as exc:
        _ = exc
        err = ManagerError(
            "INTERNAL_ERROR",
            "the command failed because of an unexpected internal error",
            "Retry the command once. If it fails again, run 'manager status --compact' and inspect diagnostic output.",
        )
        rendered_error = render_manager_error(err, store, as_json=output_json)
        print(rendered_error,file=sys.stderr)
        record_command_outcome(store, sys.argv[1:], stdin_payload, rendered_error, success=False, command_name=args.command)
        raise SystemExit(2)

if __name__=="__main__": main()
