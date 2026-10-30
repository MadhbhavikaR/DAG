"""Task identity and queue-domain rules.

This module contains deterministic domain functions and immutable-by-convention
configuration. It has no persistence or CLI dependencies.
"""

import re
from pathlib import Path


TASK_ID_RE = re.compile(r"^S(?P<story>\d{5})T(?P<task>\d{5})(?P<subs>(?:-\d{7})*)$")
QUEUE_CLASS = {
    "active": "00-ACTIVE",
    "draft": "01-DRAFT",
    "planned": "01-TODO",
    "expand": "01-TODO",
    "blocked": "02-BLOCKED",
    "done": "03-DONE",
}


def parse_task_id(value: str) -> tuple[int, int, tuple[int, ...]]:
    m = TASK_ID_RE.fullmatch(value)
    if not m:
        raise ValueError(f"invalid task ID '{value}'")
    return int(m["story"]), int(m["task"]), tuple(int(x) for x in m["subs"].split("-") if x)


def format_task_id(story: int, task: int, subs: tuple[int, ...] = ()) -> str:
    return f"S{story:05d}T{task:05d}" + "".join(f"-{x:07d}" for x in subs)


def rel_safe(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("path must be a string")
    value = value.strip()
    p = Path(value)
    if not value or p.is_absolute() or ".." in p.parts or (p.parts and p.parts[0] == ".manager"):
        raise ValueError("path must be repository-relative and cannot traverse or target .manager")
    if "\x00" in value:
        raise ValueError("path contains NUL")
    return p.as_posix()
