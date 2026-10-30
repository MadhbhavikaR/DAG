"""Execution-step data model."""

from dataclasses import dataclass, field

@dataclass
class Step:
    id: str
    task: str
    sequence: int
    status: str
    role: str
    title: str
    action: str
    accept: list[str] = field(default_factory=list)
    load: list[str] = field(default_factory=list)
    may_edit: list[str] = field(default_factory=list)
    validation: list[str] = field(default_factory=list)
    commit_policy: str = "required"
    commit_type: str = "chore"
    created: str = ""
    updated: str = ""
    result: str = "Pending"
    commit_id: str = ""
    commit_message: str = ""
    validation_event: str = ""
    commit_base_head: str = ""
