"""Task aggregate data model."""

from dataclasses import dataclass, field
from pathlib import Path

from .domain import QUEUE_CLASS, parse_task_id

@dataclass
class Task:
    path: Path
    id: str
    title: str
    parent: str | None
    sequence: int
    priority: int
    status: str
    phase: str | None = None
    current_step: str | None = None
    commit_mode: str = "disabled"
    blocker: str = ""
    created: str = ""
    updated: str = ""
    analysis: str | None = None
    decisions: str | None = None
    evidence: str | None = None
    final_validation: list[str] = field(default_factory=list)
    git_base: list[str] = field(default_factory=list)
    git_base_head: str = ""
    agent_id: str = ""
    final_commit_id: str = ""
    final_commit_message: str = ""
    body: str = ""

    @property
    def order_key(self) -> tuple[int, int, tuple[int, ...]]:
        return parse_task_id(self.id)

    @property
    def filename(self) -> str:
        q, cls = QUEUE_CLASS[self.status].split("-", 1)
        return f"TODO-{q}-{cls}-{self.priority:02d}-{self.id}.md"
