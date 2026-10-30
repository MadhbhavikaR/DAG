"""Git-backed workspace operations isolated from filesystem persistence."""

import shutil
import subprocess
from pathlib import Path

from .domain import rel_safe
from .errors import ManagerError, fail


class GitRepository:
    """Encapsulate Git discovery, inspection, and scoped commit operations."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def git_info(self) -> tuple[bool, str | None]:
        git = shutil.which("git")
        if not git:
            return False, None
        try:
            out = subprocess.run(
                [git, "-C", str(self.root), "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
            )
            return True, out.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return False, None

    def git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        git = shutil.which("git")
        if not git:
            raise ManagerError(
                "GIT_UNAVAILABLE",
                "git executable is unavailable",
                "Use a workspace without required commit gates or install git before retrying.",
            )
        return subprocess.run(
            [git, "-C", str(self.root), *args], check=check, capture_output=True, text=True
        )

    def git_status_paths(self) -> list[str]:
        if not self.git_info()[0]:
            return []
        out = self.git(["status", "--porcelain=v1", "--untracked-files=all"]).stdout
        paths: list[str] = []
        for line in out.splitlines():
            if len(line) < 4:
                continue
            raw = line[3:]
            if " -> " in raw:
                raw = raw.split(" -> ", 1)[1]
            if raw == ".manager" or raw.startswith(".manager/"):
                continue
            paths.append(raw)
        return paths

    def git_head(self) -> str:
        return self.git(["rev-parse", "HEAD"]).stdout.strip()

    def git_head_subject(self) -> str:
        return self.git(["log", "-1", "--format=%s"]).stdout.strip()

    def git_head_parent(self) -> str | None:
        out = self.git(["rev-parse", "HEAD^"], check=False)
        return out.stdout.strip() if out.returncode == 0 else None

    def git_commit_paths(self, commit: str | None = None) -> list[str]:
        ref = commit or "HEAD"
        parent = self.git(["rev-list", "--parents", "-n", "1", ref]).stdout.strip().split()
        if len(parent) > 1:
            out = self.git(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", parent[1], ref]
            ).stdout
        else:
            out = self.git(["show", "--format=", "--name-only", ref]).stdout
        return sorted(x.strip() for x in out.splitlines() if x.strip())

    def git_changed_paths_since(self, base: list[str]) -> list[str]:
        before = set(base)
        current = set(self.git_status_paths())
        return sorted(current - before)

    def git_diff_names(self, base_head: str | None = None) -> list[str]:
        if not self.git_info()[0]:
            return []
        args = ["diff", "--name-only"]
        if base_head:
            args.append(base_head)
        out = self.git(args).stdout
        return sorted(x.strip() for x in out.splitlines() if x.strip())

    def git_commit(self, paths: list[str], message: str, allow_empty: bool = False) -> str:
        if not paths and not allow_empty:
            fail(
                "EMPTY_COMMIT",
                "no permitted application changes are available to commit",
                "Implement the requested change before entering the commit phase.",
            )
        safe = [rel_safe(p) for p in paths]
        status = set(self.git_status_paths())
        unexpected = sorted(
            p for p in status - set(safe) if not (p == ".manager" or p.startswith(".manager/"))
        )
        if unexpected:
            fail(
                "DIRTY_WORKTREE",
                "working tree contains changes outside the current commit boundary: "
                + ", ".join(unexpected),
                "Restore, stash, or otherwise isolate pre-existing changes, then run 'manager next'.",
            )
        if safe:
            self.git(["add", "--", *safe])
        commit_args = ["commit", "-m", message, "--only"]
        if allow_empty:
            commit_args.append("--allow-empty")
        if safe:
            commit_args += ["--", *safe]
        self.git(commit_args)
        return self.git_head()
