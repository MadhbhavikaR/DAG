from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .domain import QUEUE_CLASS, format_task_id, parse_task_id, rel_safe
from .errors import ManagerError, fail
from .git_repository import GitRepository
from .step import Step
from .submission import Submission
from .task import Task

FORMAT_VERSION = "1.0.0"
STEP_ID_RE = re.compile(r"^STEP-\d{4}$")
RECORD_ID_RE = re.compile(r"^(FINDING|DEC|EVT)-\d{4}$")
TASK_FILE_RE = re.compile(
    r"^TODO-(?P<queue>\d{2})-(?P<class>ACTIVE|DRAFT|TODO|BLOCKED|DONE)-(?P<priority>\d{2})-(?P<id>S\d{5}T\d{5}(?:-\d{7})*)\.md$"
)
TASK_STATES = {"draft", "planned", "active", "expand", "blocked", "done"}
TASK_TRANSITIONS = {
    "draft": {"draft", "planned", "blocked"},
    "planned": {"planned", "active", "expand", "blocked"},
    "active": {"active", "expand", "blocked", "done"},
    "expand": {"expand", "active", "blocked", "done"},
    "blocked": {"blocked", "planned"},
    "done": {"done"},
}
STORY_ACTIVE_STATES = {"active", "expand", "blocked"}
PHASE_ROLE = {
    "analysis": "senior_expert",
    "planning": "planner",
    "implementation": "developer",
    "step_validation": "tester",
    "step_commit": "committer",
    "final_validation": "reviewer",
    "final_commit": "committer",
    "complete": None,
}
STEP_STATES = {
    "queued",
    "ready",
    "active",
    "implemented",
    "validating",
    "validated",
    "committing",
    "done",
    "failed",
    "blocked",
}


def now() -> str:
    return dt.datetime.now(dt.UTC).astimezone().isoformat(timespec="seconds")


def valid_timestamp(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def require_timestamp(value: str, label: str) -> None:
    if not valid_timestamp(value):
        raise ValueError(f"{label} must be an ISO-8601 timestamp with an explicit offset")


def normalize_agent_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("agent_id must be a non-empty UUID string")
    try:
        parsed = uuid.UUID(value.strip())
    except ValueError as exc:
        raise ValueError("agent_id must be a valid UUID") from exc
    if parsed.version != 4:
        raise ValueError("agent_id must be a UUIDv4")
    return str(parsed)


def generated_agent_id(task_id: str) -> str:
    _ = task_id
    return str(uuid.uuid4())


def resolve_repo_path(root: Path, value: str) -> Path:
    rel = rel_safe(value)
    target = root / rel
    resolved_root = root.resolve()
    try:
        resolved = target.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"cannot resolve path '{value}': {exc}") from exc
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("path resolves outside repository")
    if target.exists() and target.is_symlink():
        raise ValueError("symlink paths are not permitted for managed edit boundaries")
    return target


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        try:
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    finally:
        tmp.unlink(missing_ok=True)


def protect(path: Path) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(mode & ~0o222)
    except OSError:
        pass


def frontmatter(values: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if value is None:
            value = ""
        if isinstance(value, bool):
            value = "true" if value else "false"
        if isinstance(value, (list, dict)):
            raise TypeError("frontmatter values must be scalar")
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        if ":" in text and not (text.startswith("'") and text.endswith("'")):
            text = json.dumps(text)
        lines.append(f"{key}: {text}")
    lines += ["---", ""]
    return "\n".join(lines)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing frontmatter")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        raise ValueError("unterminated frontmatter")
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError("invalid frontmatter line")
        key, value = line.rstrip("\r\n").split(":", 1)
        key = key.strip()
        if key in values:
            raise ValueError(f"duplicate frontmatter field '{key}'")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid quoted frontmatter value for '{key}'") from exc
        values[key] = value
    return values, "".join(lines[end + 1 :]).lstrip("\r\n")


def list_field(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        result = json.loads(value)
        if isinstance(result, list) and all(isinstance(x, str) for x in result):
            return result
    except json.JSONDecodeError:
        pass
    return [x.strip() for x in value.split(",") if x.strip()]


def fm_value(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.git_repository = GitRepository(self.root)
        self.meta = self.root / ".manager"
        self.tasks_dir = self.meta / "tasks"
        self.steps_dir = self.meta / "steps"
        self.knowledge_dir = self.meta / "knowledge"
        self.evidence_dir = self.meta / "evidence"
        self.archive_dir = self.meta / "archive"
        self.lock_path = self.meta / ".manager.lock"
        self.submissions_path = self.meta / "submissions.json"

    def initialize_dirs(self) -> None:
        # The manager owns the entire .manager tree. A symlink at the root or
        # anywhere below it would make the ownership boundary ambiguous and
        # could redirect reads/writes outside the workspace.
        if self.meta.is_symlink():
            fail(
                "MANAGED_PATH_SYMLINK",
                ".manager is a symbolic link",
                "Replace .manager with the canonical managed directory before retrying.",
            )
        self.meta.mkdir(parents=True, exist_ok=True)
        self.reject_managed_symlinks()
        for p in (
            self.tasks_dir,
            self.steps_dir,
            self.knowledge_dir,
            self.evidence_dir,
            self.archive_dir,
        ):
            if p.is_symlink():
                fail(
                    "MANAGED_PATH_SYMLINK",
                    f"managed directory {p.relative_to(self.meta)} is a symbolic link",
                    "Replace the symbolic link with a real managed directory before retrying.",
                )
            p.mkdir(parents=True, exist_ok=True)

    def reject_managed_symlinks(self) -> None:
        if not self.meta.exists():
            return
        for path in self.meta.rglob("*"):
            if path.is_symlink():
                rel = path.relative_to(self.meta).as_posix()
                fail(
                    "MANAGED_PATH_SYMLINK",
                    f"managed path {rel} is a symbolic link",
                    "Replace the symbolic link with a canonical manager-owned file or directory before retrying.",
                )

    def workspace_id(self) -> str:
        return hashlib.sha256(str(self.root).encode()).hexdigest()[:16]

    def git_info(self) -> tuple[bool, str | None]:
        return self.git_repository.git_info()

    def commit_mode(self) -> str:
        """Return the workspace-owned commit policy, not transient Git discovery.

        The specification makes commit mode a workspace policy. Once workspace.md
        exists, later appearance/disappearance of a Git repository must not silently
        change the policy for newly created tasks. During first initialization there
        is no persisted policy yet, so Git availability determines the initial value.
        """
        workspace = self.meta / "workspace.md"
        if workspace.exists():
            try:
                fm, _ = parse_frontmatter(workspace.read_text(encoding="utf-8"))
                mode = fm.get("commit_mode")
                if mode in {"enabled", "disabled"}:
                    return mode
            except (OSError, ValueError):
                # validate() will emit the canonical corruption diagnostic.
                pass
        return "enabled" if self.git_info()[0] else "disabled"

    def initialize(self) -> None:
        # Check the persisted integrity snapshot before creating missing
        # metadata or workspace records. Otherwise a read could recreate a
        # deleted authoritative file and only then discover the mismatch.
        if self.meta.exists():
            self.reject_managed_symlinks()
            self.validate_integrity()
        self.initialize_dirs()
        version = self.meta / "VERSION"
        if version.exists() and version.read_text(encoding="utf-8").strip() != FORMAT_VERSION:
            fail(
                "UNSUPPORTED_FORMAT",
                "managed storage format is not supported",
                "Back up .manager and migrate it with a compatible manager version.",
            )
        if not version.exists():
            atomic_write(version, FORMAT_VERSION + "\n")
        workspace = self.meta / "workspace.md"
        if not workspace.exists():
            mode = self.commit_mode()
            content = (
                frontmatter(
                    {
                        "type": "workspace",
                        "format_version": FORMAT_VERSION,
                        "workspace_id": self.workspace_id(),
                        "created": now(),
                        "updated": now(),
                        "active_task": "",
                        "commit_mode": mode,
                    }
                )
                + f"# Manager Workspace\n\nRepository: {self.root}\nCommit mode: {mode}\n"
            )
            atomic_write(workspace, content)
        if not self.submissions_path.exists():
            atomic_write(self.submissions_path, "{}\n")
        # Initialization validates existing state but never reconciles or
        # repairs it. A read/startup path must not legitimize unexpected
        # managed-state changes by rewriting records or refreshing integrity.
        self.validate()
        self.rebuild_index()

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        self.initialize_dirs()
        if self.lock_path.is_symlink():
            fail(
                "MANAGED_PATH_SYMLINK",
                ".manager/.manager.lock is a symbolic link",
                "Replace the lock path with a regular manager-owned file before retrying.",
            )
        with open(self.lock_path, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def task_document(self, task: Task) -> str:
        links = {
            "analysis": task.analysis or "",
            "decisions": task.decisions or "",
            "evidence": task.evidence or "",
        }
        if not task.agent_id.strip():
            task.agent_id = generated_agent_id(task.id)
        try:
            task.agent_id = normalize_agent_id(task.agent_id)
        except ValueError as exc:
            fail(
                "CORRUPT_STATE",
                f"task {task.id} has invalid agent_id: {exc}",
                "Repair the task agent_id so it is a UUIDv4 before continuing.",
            )
        fm = {
            "type": "task",
            "format_version": FORMAT_VERSION,
            "id": task.id,
            "title": task.title,
            "parent": task.parent or "",
            "sequence": task.sequence,
            "priority": task.priority,
            "status": task.status,
            "phase": task.phase or "",
            "current_step": task.current_step or "",
            "commit_mode": task.commit_mode,
            "created": task.created,
            "updated": task.updated,
            "agent_id": task.agent_id,
            "analysis": links["analysis"],
            "decisions": links["decisions"],
            "evidence": links["evidence"],
            "blocker": task.blocker,
            "final_validation": fm_value(task.final_validation),
            "git_base": fm_value(task.git_base),
            "git_base_head": task.git_base_head,
            "final_commit_id": task.final_commit_id,
            "final_commit_message": task.final_commit_message,
        }
        body = task.body.rstrip() + "\n"
        return frontmatter(fm) + body

    def save_task(self, task: Task) -> None:
        desired = self.tasks_dir / task.filename
        if task.path.exists() and task.path != desired:
            task.path.unlink()
        task.path = desired
        atomic_write(desired, self.task_document(task))
        protect(desired)
        # Task filenames intentionally encode lifecycle state for natural directory
        # ordering. Any managed step that links back to the task must therefore be
        # rewritten atomically when that filename changes; otherwise a legal task
        # transition such as active -> blocked would leave stale step links and
        # make the workspace fail its own restart/integrity validation.
        if self.steps_dir.exists():
            for step_path in sorted(self.steps_dir.glob(f"{task.id}-STEP-*.md")):
                try:
                    step_fm, step_body = parse_frontmatter(step_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if step_fm.get("task") != f"../tasks/{desired.name}":
                    step_fm["task"] = f"../tasks/{desired.name}"
                    atomic_write(step_path, frontmatter(step_fm) + step_body)
                    protect(step_path)
        self.update_workspace_active(task.id if task.status == "active" else None)

    def update_workspace_active(self, active_hint: str | None = None) -> None:
        path = self.meta / "workspace.md"
        if not path.exists():
            return
        vals, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        active = active_hint or ""
        if not active_hint:
            tasks = self.load_tasks(validate=False)
            active_ids = [task.id for task in tasks.values() if task.status == "active"]
            active = active_ids[0] if len(active_ids) == 1 else ""
        vals["active_task"] = active
        vals["updated"] = now()
        atomic_write(path, frontmatter(vals) + body)
        protect(path)

    def load_tasks(self, validate: bool = True) -> dict[str, Task]:
        result: dict[str, Task] = {}
        if not self.tasks_dir.exists():
            return result
        for path in sorted(self.tasks_dir.glob("*.md")):
            try:
                fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
                required = {
                    "type",
                    "format_version",
                    "id",
                    "title",
                    "parent",
                    "sequence",
                    "priority",
                    "status",
                    "phase",
                    "current_step",
                    "commit_mode",
                    "created",
                    "updated",
                    "analysis",
                    "decisions",
                    "evidence",
                    "blocker",
                    "final_validation",
                    "git_base",
                    "git_base_head",
                    "final_commit_id",
                    "final_commit_message",
                    "agent_id",
                }
                missing = sorted(required - set(fm))
                if missing:
                    raise ValueError("missing required frontmatter field(s): " + ", ".join(missing))
                if fm.get("type") != "task" or fm.get("format_version") != FORMAT_VERSION:
                    raise ValueError("invalid task type or format_version")
                if not fm.get("title", "").strip():
                    raise ValueError("task title is empty")
                tid = fm.get("id", "")
                parse_task_id(tid)
                if tid in result:
                    raise ValueError(f"duplicate task ID {tid}")
                if path.name != self.expected_filename(fm):
                    raise ValueError("task filename does not match frontmatter")
                status = fm.get("status", "")
                if status not in TASK_STATES:
                    raise ValueError(f"invalid task status {status}")
                try:
                    sequence = int(fm.get("sequence", ""))
                    priority = int(fm.get("priority", ""))
                except ValueError as exc:
                    raise ValueError("sequence and priority must be integers") from exc
                if sequence <= 0 or priority < 0 or priority > 99:
                    raise ValueError(
                        "sequence must be positive and priority must be between 0 and 99"
                    )
                _, id_root, id_subs = parse_task_id(tid)
                expected_sequence = id_subs[-1] if id_subs else id_root
                if sequence != expected_sequence:
                    raise ValueError("task sequence does not agree with its identifier")
                require_timestamp(fm.get("created", ""), "created")
                require_timestamp(fm.get("updated", ""), "updated")
                if fm.get("commit_mode") not in {"enabled", "disabled"}:
                    raise ValueError("invalid commit_mode")
                raw_agent_id = fm.get("agent_id", "")
                if not isinstance(raw_agent_id, str):
                    raise TypeError("agent_id must be a UUIDv4 string")
                try:
                    agent_id = normalize_agent_id(raw_agent_id)
                except ValueError as exc:
                    raise ValueError(f"invalid task agent_id: {exc}") from exc
                # Loading managed state is a read operation. Never rewrite a
                # task record merely because its UUID representation can be
                # normalized; repairs must be explicit, validated mutations.
                phase = fm.get("phase") or None
                if phase and phase not in PHASE_ROLE:
                    raise ValueError(f"invalid phase {phase}")
                result[tid] = Task(
                    path=path,
                    id=tid,
                    title=fm.get("title", ""),
                    parent=fm.get("parent") or None,
                    sequence=sequence,
                    priority=priority,
                    status=status,
                    phase=phase,
                    current_step=fm.get("current_step") or None,
                    commit_mode=fm.get("commit_mode", "disabled"),
                    blocker=fm.get("blocker", ""),
                    created=fm.get("created", ""),
                    updated=fm.get("updated", ""),
                    analysis=fm.get("analysis") or None,
                    decisions=fm.get("decisions") or None,
                    evidence=fm.get("evidence") or None,
                    final_validation=list_field(fm.get("final_validation")),
                    git_base=list_field(fm.get("git_base")),
                    git_base_head=fm.get("git_base_head", ""),
                    agent_id=agent_id,
                    final_commit_id=fm.get("final_commit_id", ""),
                    final_commit_message=fm.get("final_commit_message", ""),
                    body=body,
                )
            except (OSError, ValueError, KeyError) as exc:
                if validate:
                    fail(
                        "CORRUPT_MANAGED_FILE",
                        f"cannot parse managed task {path.name}: {exc}",
                        "Restore the canonical managed file or use an administrative repair procedure before continuing.",
                    )
        if validate:
            self.validate_tasks(result)
        return result

    def expected_filename(self, fm: dict[str, str]) -> str:
        status = fm.get("status", "")
        if status not in QUEUE_CLASS:
            raise ValueError("invalid status")
        q, cls = QUEUE_CLASS[status].split("-", 1)
        return f"TODO-{q}-{cls}-{int(fm.get('priority', '3')):02d}-{fm['id']}.md"

    def validate_tasks(self, tasks: dict[str, Task]) -> None:
        active = [t for t in tasks.values() if t.status == "active"]
        if len(active) > 1:
            fail(
                "CORRUPT_STATE",
                "more than one task is active",
                "Resolve the managed task files with an administrative repair before continuing.",
            )
        seen_agent_ids: dict[str, str] = {}
        for t in tasks.values():
            try:
                normalized_agent_id = normalize_agent_id(t.agent_id)
            except ValueError as exc:
                fail(
                    "CORRUPT_STATE",
                    f"task {t.id} has invalid agent_id: {exc}",
                    "Repair managed task agent_id values so each task stores a UUIDv4.",
                )
            owner = seen_agent_ids.get(normalized_agent_id)
            if owner and owner != t.id:
                fail(
                    "CORRUPT_STATE",
                    f"task {t.id} reuses agent_id from {owner}",
                    "Repair managed task agent_id values so each task has a unique UUIDv4.",
                )
            seen_agent_ids[normalized_agent_id] = t.id
            if t.parent:
                if t.parent not in tasks:
                    fail(
                        "CORRUPT_STATE",
                        f"task {t.id} references missing parent {t.parent}",
                        "Restore the parent task or repair the reference before continuing.",
                    )
                if t.parent == t.id:
                    fail(
                        "CORRUPT_STATE",
                        f"task {t.id} is its own parent",
                        "Repair the managed task hierarchy before continuing.",
                    )
            if t.status == "blocked" and not t.blocker.strip():
                fail(
                    "CORRUPT_STATE",
                    f"blocked task {t.id} has no blocker",
                    "Restore the blocker field or move the task through a valid manager transition.",
                )
            if t.status in {"planned", "active", "expand"} and (
                not section_value(t.body, "WHAT") or not section_value(t.body, "DONE_WHEN")
            ):
                fail(
                    "CORRUPT_STATE",
                    f"task {t.id} is {t.status} without WHAT and DONE_WHEN",
                    "Restore the task definition with both WHAT and DONE_WHEN before continuing.",
                )
            if t.status == "active" and t.phase is None:
                fail(
                    "CORRUPT_STATE",
                    f"active task {t.id} has no execution phase",
                    "Restore the phase using a compatible manager version or repair the task.",
                )
            if t.status != "active" and t.phase not in (None, ""):
                fail(
                    "CORRUPT_STATE",
                    f"inactive task {t.id} has execution phase {t.phase}",
                    "Repair the task so only the active task carries an execution phase.",
                )
            if t.status == "done" and t.blocker.strip():
                fail(
                    "CORRUPT_STATE",
                    f"done task {t.id} retains a blocker",
                    "Repair the task so terminal tasks have no blocker.",
                )
            if t.status == "done":
                children = [c for c in tasks.values() if c.parent == t.id]
                if children and not all(c.status == "done" for c in children):
                    fail(
                        "CORRUPT_STATE",
                        f"done parent task {t.id} has incomplete or missing children",
                        "Restore the parent and child lifecycle states so every direct child is done before parent completion.",
                    )
            if t.parent:
                parent = tasks[t.parent]
                if parse_task_id(t.id)[0:2] != parse_task_id(parent.id)[0:2]:
                    fail(
                        "CORRUPT_STATE",
                        f"task {t.id} is not in its parent's story/root scope",
                        "Repair the task hierarchy before continuing.",
                    )

        # Multiple stories may coexist in the workspace, but runtime execution
        # ownership is story-scoped: only one story may hold active lifecycle
        # states (active/expand/blocked) at a time.
        active_stories = sorted(
            {parse_task_id(t.id)[0] for t in tasks.values() if t.status in STORY_ACTIVE_STATES}
        )
        if len(active_stories) > 1:
            fail(
                "CORRUPT_STATE",
                "more than one story has active lifecycle state",
                "Move tasks so only one story contains active, expand, or blocked work before continuing.",
            )

    def load_steps(self, task_id: str) -> list[Step]:
        result: list[Step] = []
        for path in sorted(self.steps_dir.glob(f"{task_id}-STEP-*.md")):
            fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            stored_task = fm.get("task_id") or fm.get("task") or ""
            expected_task_file = (
                self.load_tasks(validate=False).get(task_id).path.name
                if task_id in self.load_tasks(validate=False)
                else ""
            )
            required = {
                "type",
                "format_version",
                "id",
                "task",
                "sequence",
                "status",
                "role",
                "title",
                "commit_policy",
                "commit_type",
                "created",
                "updated",
                "commit_base_head",
            }
            missing = sorted(required - set(fm))
            if missing:
                fail(
                    "CORRUPT_MANAGED_FILE",
                    f"step {path.name} is missing frontmatter field(s): {', '.join(missing)}",
                    "Restore the canonical step file before continuing.",
                )
            if (
                fm.get("type") != "step"
                or fm.get("format_version") != FORMAT_VERSION
                or (stored_task != task_id and Path(stored_task).name != expected_task_file)
            ):
                fail(
                    "CORRUPT_MANAGED_FILE",
                    f"invalid step file {path.name}",
                    "Restore the canonical step file before continuing.",
                )
            try:
                require_timestamp(fm.get("created", ""), "step.created")
                require_timestamp(fm.get("updated", ""), "step.updated")
            except ValueError as exc:
                fail(
                    "CORRUPT_MANAGED_FILE",
                    str(exc),
                    "Restore the canonical step timestamps before continuing.",
                )
            sid = fm.get("id", "")
            if not STEP_ID_RE.fullmatch(sid):
                fail(
                    "CORRUPT_MANAGED_FILE",
                    f"invalid step ID {sid}",
                    "Restore the canonical step ID before continuing.",
                )
            try:
                sequence = int(fm.get("sequence", ""))
            except ValueError:
                fail(
                    "CORRUPT_MANAGED_FILE",
                    f"step {path.name} has a non-integer sequence",
                    "Restore the canonical step sequence before continuing.",
                )
            result.append(
                Step(
                    id=sid,
                    task=task_id,
                    sequence=sequence,
                    status=fm.get("status", ""),
                    role=fm.get("role", ""),
                    title=fm.get("title", ""),
                    action=section_value(body, "ACTION"),
                    accept=section_list(body, "ACCEPT"),
                    load=section_list(body, "LOAD"),
                    may_edit=section_list(body, "MAY_EDIT"),
                    validation=section_list(body, "VALIDATION"),
                    commit_policy=fm.get("commit_policy", "required"),
                    commit_type=fm.get("commit_type", "chore"),
                    created=fm.get("created", ""),
                    updated=fm.get("updated", ""),
                    result=section_value(body, "RESULT") or "Pending",
                    commit_id=section_value(body, "COMMIT_ID"),
                    commit_message=section_value(body, "COMMIT_MESSAGE"),
                    validation_event=section_value(body, "VALIDATION_EVENT"),
                    commit_base_head=fm.get("commit_base_head", ""),
                )
            )
        result.sort(key=lambda s: s.sequence)
        self.validate_steps(task_id, result)
        return result

    def validate_steps(self, task_id: str, steps: list[Step]) -> None:
        seen_ids: set[str] = set()
        seen_sequences: set[int] = set()
        active_states = 0
        expected_sequence = 1
        for step in steps:
            if step.id in seen_ids or step.sequence in seen_sequences:
                fail(
                    "CORRUPT_STATE",
                    f"duplicate step identity in {task_id}",
                    "Repair duplicate managed step records before continuing.",
                )
            seen_ids.add(step.id)
            seen_sequences.add(step.sequence)
            if step.sequence != expected_sequence:
                fail(
                    "CORRUPT_STATE",
                    f"step sequence is not contiguous for {task_id}: expected {expected_sequence}, found {step.sequence}",
                    "Restore canonical step ordering before continuing.",
                )
            expected_sequence += 1
            if step.status not in STEP_STATES:
                fail(
                    "CORRUPT_STATE",
                    f"invalid step state {step.status} for {step.id}",
                    "Repair the managed step state before continuing.",
                )
            if step.role != PHASE_ROLE["implementation"]:
                fail(
                    "CORRUPT_STATE",
                    f"step {step.id} has invalid role {step.role}",
                    "Restore the canonical developer role for implementation steps.",
                )
            if step.commit_policy not in {"required", "optional", "disabled"}:
                fail(
                    "CORRUPT_STATE",
                    f"step {step.id} has invalid commit policy",
                    "Restore a supported commit policy before continuing.",
                )
            if step.commit_type not in {"chore", "fix", "refactor", "test", "docs"}:
                fail(
                    "CORRUPT_STATE",
                    f"step {step.id} has invalid commit type",
                    "Restore a supported commit type before continuing.",
                )
            if (
                not step.title.strip()
                or not step.action.strip()
                or not step.accept
                or not step.validation
            ):
                fail(
                    "CORRUPT_STATE",
                    f"step {step.id} is missing canonical action, acceptance, or validation content",
                    "Restore the complete canonical step record before continuing.",
                )
            if step.commit_policy == "required" and step.status == "done" and not step.commit_id:
                fail(
                    "CORRUPT_STATE",
                    f"required-commit step {step.id} is done without a recorded commit",
                    "Restore the missing manager-created commit evidence before continuing.",
                )
            if step.status in {"ready", "active", "validating", "committing"}:
                active_states += 1
            if step.status == "queued" and step.sequence == 1:
                fail(
                    "CORRUPT_STATE",
                    f"first step {step.id} cannot remain queued",
                    "Restore the first step to active or another valid executable state.",
                )
        if active_states > 1:
            fail(
                "CORRUPT_STATE",
                f"more than one executable step is active for {task_id}",
                "Repair the managed step states before continuing.",
            )
        # Later steps remain queued until all predecessors are terminal. Only a
        # non-queued step may advance when every predecessor is done.
        for index, step in enumerate(steps):
            if step.status == "queued":
                continue
            if any(prev.status != "done" for prev in steps[:index]):
                fail(
                    "CORRUPT_STATE",
                    f"step {step.id} advanced before an earlier step completed",
                    "Restore sequential step ordering before continuing.",
                )

    def save_step(self, step: Step) -> None:
        fm = {
            "type": "step",
            "format_version": FORMAT_VERSION,
            "id": step.id,
            "task": f"../tasks/{self.load_tasks(validate=False)[step.task].path.name}"
            if step.task in self.load_tasks(validate=False)
            else step.task,
            "sequence": step.sequence,
            "status": step.status,
            "role": step.role,
            "title": step.title,
            "commit_policy": step.commit_policy,
            "commit_type": step.commit_type,
            "commit_base_head": step.commit_base_head,
            "created": step.created,
            "updated": step.updated,
        }
        body = (
            f"# {step.title}\n\nACTION:\n{step.action}\n\n"
            + "ACCEPT:\n"
            + "\n".join(f"- {x}" for x in step.accept)
            + "\n\n"
            + "LOAD:\n"
            + "\n".join(f"- {x}" for x in step.load)
            + "\n\n"
            + "MAY_EDIT:\n"
            + "\n".join(f"- {x}" for x in step.may_edit)
            + "\n\n"
            + "VALIDATION:\n"
            + "\n".join(f"- {x}" for x in step.validation)
            + "\n\n"
            + f"RESULT:\n{step.result}\n\nVALIDATION_EVENT:\n{step.validation_event}\n\n"
            + f"COMMIT_ID:\n{step.commit_id}\n\nCOMMIT_MESSAGE:\n{step.commit_message}\n"
        )
        path = self.steps_dir / f"{step.task}-{step.id}.md"
        atomic_write(path, frontmatter(fm) + body)
        protect(path)

    def save_record(self, path: Path, fm: dict[str, Any], body: str) -> None:
        atomic_write(path, frontmatter(fm) + body.rstrip() + "\n")
        protect(path)

    def append_record(self, path: Path, fm: dict[str, Any], section: str) -> None:
        if path.exists():
            oldfm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            oldfm.update(fm)
            self.save_record(path, oldfm, body.rstrip() + "\n\n" + section.rstrip() + "\n")
        else:
            self.save_record(path, fm, section.rstrip() + "\n")

    def next_step_number(self, task_id: str) -> int:
        """Return the next never-before-used step identifier for a task.

        Replanning archives superseded implementation plans under .manager/archive.
        STEP identifiers are records, not merely positions in the current plan, so
        their numeric identity must never be reused after archival.
        """
        numbers: list[int] = []
        patterns = (
            self.steps_dir.glob(f"{task_id}-STEP-*.md"),
            (self.archive_dir / task_id).rglob(f"{task_id}-STEP-*.md")
            if (self.archive_dir / task_id).exists()
            else (),
        )
        for paths in patterns:
            for path in paths:
                match = re.search(r"-STEP-(\d{4})\.md$", path.name)
                if match:
                    numbers.append(int(match.group(1)))
        return max(numbers, default=0) + 1

    def next_record_number(self, task_id: str, prefix: str) -> int:
        path = (
            self.knowledge_dir / f"{task_id}-analysis.md"
            if prefix == "FINDING"
            else self.knowledge_dir / f"{task_id}-decisions.md"
            if prefix == "DEC"
            else self.evidence_dir / f"{task_id}-evidence.md"
        )
        if not path.exists():
            return 1
        text = path.read_text(encoding="utf-8")
        nums = [int(x) for x in re.findall(rf"## {prefix}-(\d{{4}})", text)]
        return max(nums, default=0) + 1

    def allocate_task_id(
        self, tasks: dict[str, Task], parent: str | None, new_story: bool = False
    ) -> str:
        if parent:
            story, root, subs = parse_task_id(parent)
            used = [
                parse_task_id(t.id)[2][len(subs)]
                for t in tasks.values()
                if t.parent == parent and len(parse_task_id(t.id)[2]) == len(subs) + 1
            ]
            n = max(used, default=0) + 1
            return format_task_id(story, root, subs + (n,))

        # Stories are ordered work groups. A new root task joins the currently
        # open story until every task in that story is done. Once the current
        # story is complete, the next root task starts the next story. This
        # mirrors the source TODO controller's natural ordering while making
        # the story boundary manager-owned rather than model-selected.
        stories = [parse_task_id(t.id)[0] for t in tasks.values()]
        if not stories:
            story = 1
        elif new_story:
            story = max(stories) + 1
        else:
            active_stories = {
                parse_task_id(t.id)[0] for t in tasks.values() if t.status in STORY_ACTIVE_STATES
            }
            if active_stories:
                # A currently active story remains the default allocation scope
                # for normal root-task additions.
                story = min(active_stories)
            else:
                open_stories = sorted(
                    {parse_task_id(t.id)[0] for t in tasks.values() if t.status != "done"}
                )
                story = open_stories[0] if open_stories else max(stories) + 1

        roots = [
            parse_task_id(t.id)[1]
            for t in tasks.values()
            if parse_task_id(t.id)[0] == story and not parse_task_id(t.id)[2]
        ]
        return format_task_id(story, max(roots, default=0) + 1)

    def children(self, tasks: dict[str, Task], parent: str) -> list[Task]:
        return sorted([t for t in tasks.values() if t.parent == parent], key=lambda t: t.order_key)

    def git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.git_repository.git(args, check=check)

    def git_status_paths(self) -> list[str]:
        return self.git_repository.git_status_paths()

    def git_head(self) -> str:
        return self.git_repository.git_head()

    def git_head_subject(self) -> str:
        return self.git_repository.git_head_subject()

    def git_head_parent(self) -> str | None:
        return self.git_repository.git_head_parent()

    def git_commit_paths(self, commit: str | None = None) -> list[str]:
        return self.git_repository.git_commit_paths(commit)

    def git_changed_paths_since(self, base: list[str]) -> list[str]:
        return self.git_repository.git_changed_paths_since(base)

    def git_diff_names(self, base_head: str | None = None) -> list[str]:
        return self.git_repository.git_diff_names(base_head)

    def git_commit(self, paths: list[str], message: str, allow_empty: bool = False) -> str:
        return self.git_repository.git_commit(paths, message, allow_empty=allow_empty)

    def rebuild_index(self) -> None:
        tasks = self.load_tasks(validate=False)
        lines = [
            frontmatter({"type": "index", "format_version": FORMAT_VERSION, "updated": now()}),
            "# Manager Index",
            "",
        ]
        for t in sorted(tasks.values(), key=lambda x: x.order_key):
            lines.append(f"- [{t.id}]({Path('tasks') / t.path.name}) — {t.status} — {t.title}")
        atomic_write(self.meta / "index.md", "\n".join(lines).rstrip() + "\n")
        protect(self.meta / "index.md")

    def validate(self) -> None:
        if not self.meta.exists():
            return
        self.reject_managed_symlinks()
        self.validate_integrity()
        version = self.meta / "VERSION"
        if version.exists() and version.read_text(encoding="utf-8").strip() != FORMAT_VERSION:
            fail(
                "UNSUPPORTED_FORMAT",
                "unsupported .manager VERSION",
                "Use a compatible manager or migrate the managed workspace.",
            )
        self.validate_workspace()
        tasks = self.load_tasks(validate=False)
        self.validate_tasks(tasks)
        steps_by_task = {}
        for tid in tasks:
            steps_by_task[tid] = self.load_steps(tid)
        self.validate_execution_consistency(tasks, steps_by_task)
        self.validate_references(tasks)
        self.validate_supporting_records(tasks)
        self.validate_submission_ledger()

    def validate_workspace(self) -> None:
        path = self.meta / "workspace.md"
        if not path.exists():
            fail(
                "CORRUPT_STATE",
                "workspace.md is missing",
                "Restore the canonical workspace record before continuing.",
            )
        try:
            fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fail(
                "CORRUPT_MANAGED_FILE",
                f"cannot parse workspace.md: {exc}",
                "Restore the canonical workspace record before continuing.",
            )
        required = {
            "type",
            "format_version",
            "workspace_id",
            "created",
            "updated",
            "active_task",
            "commit_mode",
        }
        missing = sorted(required - set(fm))
        if missing:
            fail(
                "CORRUPT_MANAGED_FILE",
                "workspace.md is missing frontmatter field(s): " + ", ".join(missing),
                "Restore the canonical workspace record before continuing.",
            )
        if fm.get("type") != "workspace" or fm.get("format_version") != FORMAT_VERSION:
            fail(
                "CORRUPT_MANAGED_FILE",
                "workspace.md has an invalid type or format_version",
                "Restore the canonical workspace record before continuing.",
            )
        if fm.get("workspace_id") != self.workspace_id():
            fail(
                "CORRUPT_MANAGED_FILE",
                "workspace_id does not match the repository root",
                "Restore the canonical workspace record for this repository before continuing.",
            )
        try:
            require_timestamp(fm.get("created", ""), "workspace.created")
            require_timestamp(fm.get("updated", ""), "workspace.updated")
        except ValueError as exc:
            fail(
                "CORRUPT_MANAGED_FILE",
                str(exc),
                "Restore workspace.md with canonical ISO-8601 timestamps including an explicit offset.",
            )
        if fm.get("commit_mode") not in {"enabled", "disabled"}:
            fail(
                "CORRUPT_MANAGED_FILE",
                "workspace.md has an invalid commit_mode",
                "Restore commit_mode to enabled or disabled before continuing.",
            )

    def validate_execution_consistency(
        self, tasks: dict[str, Task], steps_by_task: dict[str, list[Step]]
    ) -> None:
        for task in tasks.values():
            steps = steps_by_task.get(task.id, [])
            if task.status != "active":
                executable_states = {
                    "ready",
                    "active",
                    "implemented",
                    "validating",
                    "validated",
                    "committing",
                }
                if (
                    steps
                    and task.phase in {None, "complete"}
                    and any(s.status in executable_states for s in steps)
                ):
                    fail(
                        "CORRUPT_STATE",
                        f"inactive task {task.id} has executable unfinished steps",
                        "Restore the task and step lifecycle to a legal state before continuing.",
                    )
                continue
            if task.phase == "analysis":
                if steps:
                    fail(
                        "CORRUPT_STATE",
                        f"analysis task {task.id} already has implementation steps",
                        "Restore the task to a phase consistent with its plan before continuing.",
                    )
            elif task.phase == "planning":
                if steps and any(s.status not in {"done", "failed", "blocked"} for s in steps):
                    fail(
                        "CORRUPT_STATE",
                        f"planning task {task.id} has unfinished implementation steps",
                        "Restore the task to planning with all prior steps terminal before continuing.",
                    )
            elif task.phase in {"implementation", "step_validation", "step_commit"}:
                if not task.current_step:
                    fail(
                        "CORRUPT_STATE",
                        f"{task.phase} task {task.id} has no current_step",
                        "Restore the current step reference before continuing.",
                    )
                current = [s for s in steps if s.id == task.current_step]
                if len(current) != 1:
                    fail(
                        "CORRUPT_STATE",
                        f"{task.id} references missing or duplicate current step {task.current_step}",
                        "Restore the canonical current step reference before continuing.",
                    )
                step = current[0]
                expected = {
                    "implementation": {"active", "ready"},
                    "step_validation": {"validating"},
                    "step_commit": {"validated", "committing"},
                }[task.phase]
                if step.status not in expected:
                    fail(
                        "CORRUPT_STATE",
                        f"{task.id} phase {task.phase} disagrees with step {step.id} state {step.status}",
                        "Restore the task phase and current step to a legal execution state before continuing.",
                    )
            elif task.phase == "final_validation":
                if task.current_step:
                    fail(
                        "CORRUPT_STATE",
                        f"final-validation task {task.id} still has current_step {task.current_step}",
                        "Clear current_step before final validation can begin.",
                    )
                if steps and not all(s.status == "done" for s in steps):
                    fail(
                        "CORRUPT_STATE",
                        f"final-validation task {task.id} has incomplete implementation steps",
                        "Complete every implementation step before entering final validation.",
                    )
            elif task.phase == "final_commit":
                if task.current_step:
                    fail(
                        "CORRUPT_STATE",
                        f"final-commit task {task.id} still has current_step {task.current_step}",
                        "Clear current_step before final commit can begin.",
                    )
                if steps and not all(s.status == "done" for s in steps):
                    fail(
                        "CORRUPT_STATE",
                        f"final-commit task {task.id} has incomplete implementation steps",
                        "Complete every implementation step before entering final commit.",
                    )
                evidence = task.evidence
                if not evidence or not (task.path.parent / evidence).resolve().exists():
                    fail(
                        "CORRUPT_STATE",
                        f"final-commit task {task.id} has no evidence record",
                        "Restore the task evidence before continuing.",
                    )
            elif task.phase not in PHASE_ROLE:
                fail(
                    "CORRUPT_STATE",
                    f"task {task.id} has unsupported phase {task.phase}",
                    "Restore a supported execution phase before continuing.",
                )

    def validate_supporting_records(self, tasks: dict[str, Task]) -> None:
        """Validate lazy analysis, decision, and evidence projections as authoritative records.

        Supporting documents are manager-owned state. They are intentionally lazy, but once
        present they must have canonical identity, ownership, timestamps, and append-only
        record identities that cannot silently collide or change lifecycle semantics.
        """
        for task_id in tasks:
            for kind, path, expected_id in (
                ("analysis", self.knowledge_dir / f"{task_id}-analysis.md", f"{task_id}-ANALYSIS"),
                (
                    "decisions",
                    self.knowledge_dir / f"{task_id}-decisions.md",
                    f"{task_id}-DECISIONS",
                ),
                ("evidence", self.evidence_dir / f"{task_id}-evidence.md", f"{task_id}-EVIDENCE"),
            ):
                if not path.exists():
                    continue
                if path.stat().st_size == 0:
                    fail(
                        "CORRUPT_MANAGED_FILE",
                        f"{path.name} is empty",
                        "Restore the managed record or remove it through an administrative repair procedure.",
                    )
                try:
                    fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    fail(
                        "CORRUPT_MANAGED_FILE",
                        f"{path.name} has invalid frontmatter: {exc}",
                        "Restore the managed supporting record from a trusted manager snapshot.",
                    )
                required = {"type", "format_version", "id", "task_id", "created", "updated"}
                if set(fm) != required:
                    fail(
                        "CORRUPT_MANAGED_FILE",
                        f"{path.name} has an invalid frontmatter schema",
                        "Restore the canonical supporting-record frontmatter before continuing.",
                    )
                if (
                    fm["type"] != kind
                    or fm["format_version"] != FORMAT_VERSION
                    or fm["id"] != expected_id
                    or fm["task_id"] != task_id
                ):
                    fail(
                        "CORRUPT_MANAGED_FILE",
                        f"{path.name} has inconsistent identity metadata",
                        "Restore the canonical type, format version, record ID, and task ID.",
                    )
                require_timestamp(fm["created"], f"{path.name}.created")
                require_timestamp(fm["updated"], f"{path.name}.updated")
                if not body.strip():
                    fail(
                        "CORRUPT_MANAGED_FILE",
                        f"{path.name} contains no record content",
                        "Restore the supporting record content before continuing.",
                    )

                if kind == "analysis":
                    ids = re.findall(r"^## (FINDING-\d{4})$", body, flags=re.MULTILINE)
                    if len(ids) != len(set(ids)):
                        fail(
                            "CORRUPT_MANAGED_FILE",
                            f"{path.name} contains duplicate finding IDs",
                            "Restore unique FINDING-#### record IDs before continuing.",
                        )
                    for rid in ids:
                        chunk = body.split(f"## {rid}\n", 1)[1].split("\n## ", 1)[0]
                        for heading in ("QUESTION", "FINDING", "EVIDENCE", "IMPACT", "CONFIDENCE"):
                            if not section_value(chunk, heading):
                                fail(
                                    "CORRUPT_MANAGED_FILE",
                                    f"{path.name} record {rid} is missing {heading}",
                                    "Restore the complete canonical finding record before continuing.",
                                )
                elif kind == "decisions":
                    ids = re.findall(r"^## (DEC-\d{4})$", body, flags=re.MULTILINE)
                    if len(ids) != len(set(ids)):
                        fail(
                            "CORRUPT_MANAGED_FILE",
                            f"{path.name} contains duplicate decision IDs",
                            "Restore unique DEC-#### record IDs before continuing.",
                        )
                    for rid in ids:
                        chunk = body.split(f"## {rid}\n", 1)[1].split("\n## ", 1)[0]
                        status_match = re.search(r"^STATUS:\n([^\n]+)", chunk, flags=re.MULTILINE)
                        if not status_match or status_match.group(1).strip() not in {
                            "proposed",
                            "accepted",
                            "rejected",
                            "superseded",
                        }:
                            fail(
                                "CORRUPT_MANAGED_FILE",
                                f"{path.name} decision {rid} has an invalid status",
                                "Restore the decision lifecycle to proposed, accepted, rejected, or superseded.",
                            )
                        for heading in ("DECISION", "RATIONALE"):
                            if not section_value(chunk, heading):
                                fail(
                                    "CORRUPT_MANAGED_FILE",
                                    f"{path.name} decision {rid} is missing {heading}",
                                    "Restore the complete canonical decision record before continuing.",
                                )
                        for heading in ("ALTERNATIVES", "CONSEQUENCES", "EVIDENCE", "SUPERSEDES"):
                            if (
                                re.search(
                                    r"^" + re.escape(heading) + r":", chunk, flags=re.MULTILINE
                                )
                                is None
                            ):
                                fail(
                                    "CORRUPT_MANAGED_FILE",
                                    f"{path.name} decision {rid} is missing {heading}",
                                    "Restore the complete canonical decision record before continuing.",
                                )
                    resolutions = re.findall(
                        r"^## DECISION-RESOLUTION-(DEC-\d{4})$", body, flags=re.MULTILINE
                    )
                    if len(resolutions) != len(set(resolutions)):
                        fail(
                            "CORRUPT_MANAGED_FILE",
                            f"{path.name} contains duplicate decision resolution IDs",
                            "Restore unique decision resolution records before continuing.",
                        )
                    for rid in resolutions:
                        if rid not in ids:
                            fail(
                                "CORRUPT_MANAGED_FILE",
                                f"{path.name} resolves unknown decision {rid}",
                                "Restore the referenced decision before continuing.",
                            )
                        matches = re.findall(
                            r"## DECISION-RESOLUTION-"
                            + re.escape(rid)
                            + r"\n\nDECISION_ID:\n"
                            + re.escape(rid)
                            + r"\n\nSTATUS:\n([^\n]+)",
                            body,
                        )
                        if not matches or matches[-1] not in {"accepted", "rejected", "superseded"}:
                            fail(
                                "CORRUPT_MANAGED_FILE",
                                f"{path.name} has an invalid resolution for {rid}",
                                "Restore the decision resolution lifecycle before continuing.",
                            )
                else:
                    ids = re.findall(r"^## (EVT-\d{4})$", body, flags=re.MULTILINE)
                    if len(ids) != len(set(ids)):
                        fail(
                            "CORRUPT_MANAGED_FILE",
                            f"{path.name} contains duplicate evidence IDs",
                            "Restore unique EVT-#### record IDs before continuing.",
                        )
                    for rid in ids:
                        chunk = body.split(f"## {rid}\n", 1)[1].split("\n## ", 1)[0]
                        if not re.search(
                            r"^TYPE:\n\S+", chunk, flags=re.MULTILINE
                        ) or not re.search(r"^RECORDED_AT:\n\S+", chunk, flags=re.MULTILINE):
                            fail(
                                "CORRUPT_MANAGED_FILE",
                                f"{path.name} evidence {rid} is missing canonical metadata",
                                "Restore TYPE and RECORDED_AT for the evidence record before continuing.",
                            )
                        recorded = re.search(r"^RECORDED_AT:\n([^\n]+)", chunk, flags=re.MULTILINE)
                        if recorded:
                            require_timestamp(
                                recorded.group(1).strip(), f"{path.name} {rid}.RECORDED_AT"
                            )

    def validate_submission_ledger(self) -> None:
        if not self.submissions_path.exists():
            fail(
                "CORRUPT_STATE",
                "submission ledger is missing",
                "Restore submissions.json from a trusted manager snapshot before continuing.",
            )
        try:
            raw = json.loads(self.submissions_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(
                "CORRUPT_STATE",
                f"submission ledger is malformed: {exc}",
                "Restore submissions.json from a trusted manager snapshot before continuing.",
            )
        if not isinstance(raw, dict):
            fail(
                "CORRUPT_STATE",
                "submission ledger must contain an object",
                "Restore submissions.json with the canonical object structure.",
            )
        for token, record in raw.items():
            if not isinstance(token, str) or not token:
                fail(
                    "CORRUPT_STATE",
                    "submission ledger contains an invalid token",
                    "Restore submissions.json with non-empty string tokens.",
                )
            if not isinstance(record, dict) or set(record) != {"token", "fingerprint", "response"}:
                fail(
                    "CORRUPT_STATE",
                    f"submission ledger entry {token!r} has an invalid schema",
                    "Restore the malformed submission entry before continuing.",
                )
            if (
                record.get("token") != token
                or not isinstance(record.get("fingerprint"), str)
                or not isinstance(record.get("response"), str)
            ):
                fail(
                    "CORRUPT_STATE",
                    f"submission ledger entry {token!r} has invalid field types",
                    "Restore the malformed submission entry before continuing.",
                )
            if not re.fullmatch(r"[0-9a-f]{64}", record["fingerprint"]):
                fail(
                    "CORRUPT_STATE",
                    f"submission ledger entry {token!r} has an invalid fingerprint",
                    "Restore the canonical submission fingerprint before continuing.",
                )

    def validate_references(self, tasks: dict[str, Task]) -> None:
        for t in tasks.values():
            for field_name, rel in (
                ("analysis", t.analysis),
                ("decisions", t.decisions),
                ("evidence", t.evidence),
            ):
                if rel:
                    target = (t.path.parent / rel).resolve()
                    if not target.is_relative_to(self.meta.resolve()):
                        fail(
                            "CORRUPT_STATE",
                            f"{t.id} {field_name} link escapes .manager",
                            "Repair the managed link before continuing.",
                        )
                    if not target.exists():
                        fail(
                            "CORRUPT_STATE",
                            f"{t.id} references missing {field_name} file",
                            "Restore the referenced managed record or repair the link.",
                        )

    def refresh_integrity(self) -> None:
        records = {}
        if not self.meta.exists():
            return
        for path in sorted(self.meta.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.meta).as_posix()
            if integrity_ignored(rel, path.name):
                continue
            records[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        atomic_write(
            self.meta / "integrity.json", json.dumps(records, indent=2, sort_keys=True) + "\n"
        )
        protect(self.meta / "integrity.json")

    def validate_integrity(self) -> None:
        path = self.meta / "integrity.json"
        if not path.exists():
            return
        try:
            expected = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(
                "CORRUPT_STATE",
                f"integrity manifest is malformed: {exc}",
                "Restore integrity.json from a trusted manager snapshot before continuing.",
            )
        if not isinstance(expected, dict) or any(
            not isinstance(rel_path, str)
            or not rel_path
            or Path(rel_path).is_absolute()
            or ".." in Path(rel_path).parts
            or "\\" in rel_path
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for rel_path, digest in expected.items()
        ):
            fail(
                "CORRUPT_STATE",
                "integrity manifest must map safe relative paths to SHA-256 digests",
                "Restore integrity.json from a trusted manager snapshot before continuing.",
            )
        actual = {}
        for p in sorted(self.meta.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(self.meta).as_posix()
            if integrity_ignored(rel, p.name):
                continue
            actual[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        if expected != actual:
            missing = sorted(set(expected) - set(actual))
            added = sorted(set(actual) - set(expected))
            changed = sorted(k for k in set(expected) & set(actual) if expected[k] != actual[k])
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if added:
                detail.append("added=" + ",".join(added))
            if changed:
                detail.append("changed=" + ",".join(changed))
            fail(
                "MANAGED_FILE_TAMPERED",
                "managed-file integrity check failed: " + "; ".join(detail),
                "Restore the affected .manager files from the last trusted manager snapshot, then rerun the command.",
            )

    def load_submissions(self) -> dict[str, Submission]:
        self.validate_submission_ledger()
        raw = json.loads(self.submissions_path.read_text(encoding="utf-8"))
        return {k: Submission(k, v["fingerprint"], v["response"]) for k, v in raw.items()}

    def remember_submission(self, token: str, payload: dict[str, Any], response: str) -> str:
        ledger = self.load_submissions()
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if token in ledger:
            if ledger[token].fingerprint != fingerprint:
                fail(
                    "TOKEN_REUSE",
                    "submission token was already used with different content",
                    "Generate a new submission token and resubmit the current result.",
                )
            return ledger[token].response
        ledger[token] = Submission(token, fingerprint, response)
        atomic_write(
            self.submissions_path,
            json.dumps({k: vars(v) for k, v in ledger.items()}, indent=2, sort_keys=True) + "\n",
        )
        protect(self.submissions_path)
        return response


def section_value(body: str, heading: str) -> str:
    marker = heading + ":"
    pattern = re.compile(
        r"^" + re.escape(marker) + r"\n(.*?)(?=\n\n[A-Z][A-Z_]*:|\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def section_list(body: str, heading: str) -> list[str]:
    marker = heading + ":"
    if marker not in body:
        return []
    rest = body.split(marker, 1)[1].lstrip("\n")
    chunk = rest.split("\n\n", 1)[0]
    return [x[2:].strip() for x in chunk.splitlines() if x.startswith("- ")]


def integrity_ignored(rel_path: str, name: str) -> bool:
    if name in {".manager.lock", "integrity.json", "index.md"}:
        return True
    # Runtime helper artifacts (schema cache, error telemetry) are manager-owned
    # diagnostics and should not fail strict state integrity checks.
    return rel_path.startswith(("runtime/", "logs/"))
