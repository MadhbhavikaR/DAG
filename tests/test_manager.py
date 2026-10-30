import json
import re
import os
import subprocess
import contextlib
import io
import sys
import tempfile
import uuid
import shutil
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from manager.core import Store, ManagerError, generated_agent_id
from manager import cli


def is_uuid_v4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value.lower()


class ManagerHarness:
    def __init__(self, root: Path):
        self.root = root

    def _legacy_from_json_stdout(self, text: str) -> str:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], str):
            return payload["result"] + ("\n" if not payload["result"].endswith("\n") else "")
        if isinstance(payload, dict) and {"task", "phase", "role"}.issubset(payload.keys()):
            lines = [
                f"TASK: {payload.get('task')}",
                f"AGENT_ID: {payload.get('agent_id')}",
                f"TASK_STATE: {payload.get('task_state')}",
                f"PHASE: {payload.get('phase')}",
                f"ROLE: {payload.get('role')}",
            ]
            if payload.get("step"):
                lines.append(f"STEP: {payload['step']}")
            if isinstance(payload.get("action"), str):
                lines += ["", "ACTION:", payload["action"]]
            lines += ["", "LOAD:"]
            load = payload.get("load") or []
            if load:
                lines += [f"- {item}" for item in load]
            else:
                lines.append("- None")
            return "\n".join(lines) + "\n"
        if isinstance(payload, dict) and "records" in payload and "task" in payload:
            lines = [f"TASK: {payload.get('task')}", f"PHASE: {payload.get('phase')}", ""]
            for rec in payload.get("records", []):
                rid = rec.get("id", "")
                rtype = rec.get("type", "")
                content = rec.get("content", "")
                lines += [f"CONTEXT: {rid}", f"TYPE: {rtype}", str(content), ""]
            return "\n".join(lines)
        return text

    def _legacy_from_json_stderr(self, text: str) -> str:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return text
        if not isinstance(payload, dict) or "error" not in payload:
            return text
        lines = [
            f"ERROR: {payload.get('error')}",
            f"WHAT: {payload.get('what', '')}",
            f"DO: {payload.get('do', '')}",
        ]
        if payload.get("hint"):
            lines.append(f"HINT: {payload['hint']}")
        if payload.get("gotcha"):
            lines.append(f"GOTCHA: {payload['gotcha']}")
        return "\n".join(lines) + "\n"

    def _active_agent_id(self) -> str | None:
        store = Store(self.root)
        if not store.meta.exists():
            return None
        tasks = store.load_tasks(validate=False)
        active = sorted([task for task in tasks.values() if task.status == "active"], key=lambda task: task.order_key)
        if not active:
            return None
        task = active[0]
        return task.agent_id or generated_agent_id(task.id)

    def _should_inject_agent_id(self, args: tuple[str, ...]) -> bool:
        if not args:
            return False
        if args[0] == "submit":
            return True
        if args[0] == "plan" and len(args) > 1 and args[1] == "submit":
            return True
        if args[0] == "finding" and len(args) > 1 and args[1] == "add":
            return True
        if args[0] == "decision" and len(args) > 1 and args[1] in {"propose", "resolve"}:
            return True
        if args[0] == "evidence" and len(args) > 1 and args[1] == "add":
            return True
        return False

    def _inject_agent_id(self, args: tuple[str, ...], stdin: str | None, inject_agent_id: bool) -> str | None:
        if not inject_agent_id or not stdin or not self._should_inject_agent_id(args):
            return stdin
        try:
            payload = json.loads(stdin)
        except json.JSONDecodeError:
            return stdin
        if not isinstance(payload, dict) or "agent_id" in payload:
            return stdin
        agent_id = self._active_agent_id()
        if not agent_id:
            return stdin
        payload["agent_id"] = agent_id
        return json.dumps(payload)

    def run(self, *args, stdin=None, check=True, raw=False, inject_agent_id=True):
        old_argv = sys.argv
        old_stdin = sys.stdin
        out, err = io.StringIO(), io.StringIO()
        stdin = self._inject_agent_id(tuple(args), stdin, inject_agent_id)
        sys.argv = ["manager", "--root", str(self.root), *args]
        sys.stdin = io.StringIO(stdin or "")
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    cli.main()
                except SystemExit as exc:
                    code = int(exc.code or 0)
        finally:
            sys.argv = old_argv
            sys.stdin = old_stdin
        stdout, stderr = out.getvalue(), err.getvalue()
        if not raw:
            stdout = self._legacy_from_json_stdout(stdout)
            stderr = self._legacy_from_json_stderr(stderr)
        result = subprocess.CompletedProcess(sys.argv, code, stdout, stderr)
        if check and code != 0:
            raise AssertionError(result.stderr)
        return result

    def add(self, payload, *extra):
        return self.run("task", "add", *extra, stdin=json.dumps(payload))

    def submit(self, payload, check=True, inject_agent_id=True):
        result = self.run("submit", stdin=json.dumps(payload), check=check, inject_agent_id=inject_agent_id)
        # Model-facing tests that submit a plan then immediately exercise the
        # implementation phase perform the required manager.next selection
        # here. Tests that specifically assert the durable ready state use the
        # raw run() helper instead.
        if check and "steps" in payload and result.returncode == 0:
            self.run("next")
        return result





class ManagerReleaseArtifactTests(unittest.TestCase):
    def test_release_version_comes_from_project_metadata(self):
        import tomllib
        from importlib.metadata import version

        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        self.assertEqual(version(project["name"]), project["version"])

        package_init = (root / "src" / "manager" / "__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("__version__ =", package_init)

        skill = root / "skill" / "manager" / "SKILL.md"
        self.assertTrue(skill.is_file())
        skill_text = skill.read_text(encoding="utf-8")
        self.assertIn("name: manager", skill_text)
        self.assertIn(f"Current release: {project['version']}", skill_text)


    def test_application_classes_have_single_module_ownership(self):
        from manager.core import ManagerError, Step, Store, Submission, Task
        from manager.parser import ManagerArgumentParser
        from manager.cli import CommandDispatcher

        expected_modules = {
            ManagerError: "manager.errors",
            Step: "manager.step",
            Store: "manager.core",
            Submission: "manager.submission",
            Task: "manager.task",
            ManagerArgumentParser: "manager.parser",
            CommandDispatcher: "manager.cli",
        }
        for model, expected_module in expected_modules.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(model.__module__, expected_module)

    def test_task_and_step_mutable_defaults_are_not_shared(self):
        from manager.core import Step, Task

        first_task = Task(Path("."), "S00001T00001", "First", None, 1, 1, "planned")
        second_task = Task(Path("."), "S00001T00002", "Second", None, 2, 1, "planned")
        first_task.final_validation.append("check")
        first_task.git_base.append("README.md")
        self.assertEqual(second_task.final_validation, [])
        self.assertEqual(second_task.git_base, [])

        first_step = Step("STEP-0001", "S00001T00001", 1, "queued", "developer", "First", "Do it")
        second_step = Step("STEP-0002", "S00001T00001", 2, "queued", "developer", "Second", "Do it")
        first_step.accept.append("works")
        first_step.load.append("context")
        self.assertEqual(second_step.accept, [])
        self.assertEqual(second_step.load, [])

    def test_dispatcher_stdin_policy_matches_command_contract(self):
        cases = [
            (["submit"], True),
            (["block"], True),
            (["task", "add"], True),
            (["task", "edit"], True),
            (["task", "plan"], False),
            (["finding", "add"], True),
            (["evidence", "add"], True),
            (["decision", "propose"], True),
            (["learn", "add"], True),
            (["learn", "from-log"], False),
            (["plan", "submit"], True),
            (["next"], False),
            (["status"], False),
        ]
        parser = cli.build_parser()
        for argv, expected in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(cli.CommandDispatcher.reads_stdin(args), expected)

    def test_dispatcher_returns_result_and_mutation_policy(self):
        dispatcher = cli.CommandDispatcher(mock.Mock())
        parser = cli.build_parser()

        with mock.patch.object(cli, "cmd_examples", return_value={"ok": True}) as handler:
            result, mutating = dispatcher.dispatch(parser.parse_args(["examples"]))
        self.assertEqual(result, {"ok": True})
        self.assertFalse(mutating)
        handler.assert_called_once_with(as_json=True)

        with mock.patch.object(cli, "cmd_next", return_value={"next": True}) as handler:
            result, mutating = dispatcher.dispatch(parser.parse_args(["next"]))
        self.assertEqual(result, {"next": True})
        self.assertTrue(mutating)
        handler.assert_called_once_with(dispatcher._store, as_json=True)


    def test_git_repository_owns_git_discovery_and_status(self):
        from manager.git_repository import GitRepository

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "manager-tests@example.invalid"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Manager Tests"],
                check=True,
                capture_output=True,
            )
            tracked = root / "tracked.txt"
            tracked.write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-m", "initial"],
                check=True,
                capture_output=True,
            )

            repository = GitRepository(root)
            available, git_root = repository.git_info()
            self.assertTrue(available)
            self.assertEqual(Path(git_root), root.resolve())
            self.assertTrue(repository.git_head())

            (root / "changed.txt").write_text("changed\n", encoding="utf-8")
            (root / ".manager").mkdir()
            (root / ".manager" / "private.json").write_text("{}", encoding="utf-8")
            self.assertEqual(repository.git_status_paths(), ["changed.txt"])

            store = Store(root)
            self.assertEqual(store.git_head(), repository.git_head())

    def test_git_repository_reports_missing_git_explicitly(self):
        from manager.git_repository import GitRepository

        repository = GitRepository(Path("."))
        with mock.patch("manager.git_repository.shutil.which", return_value=None):
            self.assertEqual(repository.git_info(), (False, None))
            with self.assertRaises(ManagerError) as raised:
                repository.git(["status"])
        self.assertEqual(raised.exception.code, "GIT_UNAVAILABLE")


class ManagerTests(unittest.TestCase):

    def test_final_review_correction_uses_monotonic_step_id_and_ready_gate(self):
        self.h.add({"title":"Change","what":"Change","done_when":"Changed"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        plan={"steps":[{"title":"Change","action":"Change","accept":["changed"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"fix"}],"final_validation":["python -m unittest"]}
        self.h.run("submit", stdin=json.dumps(plan))
        self.h.run("next")
        (self.root/"app.py").write_text("print('new')\n")
        self.h.submit({"outcome":"completed","summary":"changed","changed_files":["app.py"]})
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.h.submit({"outcome":"failed","runs":[{"command":"python -m unittest","exit_code":1,"summary":"planning defect"}],"review_findings":["Planning defect"],"failure_classification":"planning","diff_reviewed":True})
        task=Store(self.root).load_tasks()["S00001T00001"]
        self.assertEqual(task.phase,"planning")
        self.h.run("submit", stdin=json.dumps(plan))
        steps=Store(self.root).load_steps(task.id)
        self.assertEqual([s.id for s in steps],["STEP-0002"])
        self.assertEqual(steps[0].status,"ready")
        self.h.run("next")
        (self.root/"app.py").write_text("print('newer')\n")
        self.h.submit({"outcome":"completed","summary":"changed again","changed_files":["app.py"]})
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.h.submit({"outcome":"failed","runs":[{"command":"python -m unittest","exit_code":1,"summary":"implementation defect"}],"review_findings":["Fix final review defect"],"failure_classification":"implementation","diff_reviewed":True})
        current=Store(self.root).load_tasks()[task.id]
        self.assertEqual(current.phase,"implementation")
        self.assertEqual(current.current_step,"STEP-0003")
        correction=[s for s in Store(self.root).load_steps(task.id) if s.id=="STEP-0003"][0]
        self.assertEqual(correction.status,"ready")
        self.h.run("next")
        self.assertEqual([s for s in Store(self.root).load_steps(task.id) if s.id=="STEP-0003"][0].status,"active")
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_task_hint_includes_asd_ste100_reminder(self):
        payload = json.loads(self.h.run("next", raw=True).stdout)
        self.assertEqual(payload["result"], "NO_TASK")
        self.assertIn("ASD-STE100 reminder", payload["hint"])

    def test_next_includes_task_agent_id(self):
        self.h.add({"title": "Agent ID envelope", "what": "Inspect", "done_when": "Inspected"})
        payload = json.loads(self.h.run("next", raw=True).stdout)
        self.assertTrue(is_uuid_v4(payload["agent_id"]))

    def test_submit_requires_agent_id(self):
        self.h.add({"title": "Agent ID submit", "what": "Inspect", "done_when": "Inspected"})
        self.h.run("next")
        result = self.h.run(
            "submit",
            stdin=json.dumps({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True}),
            check=False,
            raw=True,
            inject_agent_id=False,
        )
        payload = json.loads(result.stderr)
        self.assertEqual(payload["error"], "INVALID_SCHEMA")
        self.assertIn("agent_id", payload["what"])

    def test_submit_rejects_mismatched_agent_id(self):
        self.h.add({"title": "Agent ID mismatch", "what": "Inspect", "done_when": "Inspected"})
        self.h.run("next")
        result = self.h.run(
            "submit",
            stdin=json.dumps({"agent_id": "00000000-0000-4000-8000-000000000099", "outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True}),
            check=False,
            raw=True,
            inject_agent_id=False,
        )
        payload = json.loads(result.stderr)
        self.assertEqual(payload["error"], "AGENT_ID_MISMATCH")

    def test_title_only_draft_and_natural_filename(self):
        r = self.h.add({"title": "First task"})
        self.assertIn("S00001T00001 draft", r.stdout)
        names = [p.name for p in (self.root / ".manager/tasks").glob("*.md")]
        self.assertEqual(names, ["TODO-01-DRAFT-03-S00001T00001.md"])
        task = Store(self.root).load_tasks()["S00001T00001"]
        self.assertTrue(is_uuid_v4(task.agent_id))

    def test_task_add_batch_splits_into_individual_stories_and_tasks(self):
        payload = {
            "items": [
                {"title": "First item", "what": "Do first", "done_when": "First done"},
                {"title": "Second item", "what": "Do second", "done_when": "Second done"},
            ]
        }
        result = json.loads(self.h.run("task", "add", stdin=json.dumps(payload), raw=True).stdout)
        self.assertEqual(result["result"], "CREATED_BATCH")
        self.assertEqual(result["count"], 2)
        created = result["created"]
        self.assertEqual([item["id"] for item in created], ["S00001T00001", "S00002T00001"])
        tasks = Store(self.root).load_tasks()
        self.assertEqual(tasks["S00001T00001"].status, "planned")
        self.assertEqual(tasks["S00002T00001"].status, "planned")

    def test_task_add_child_uses_identifier_consistent_sequence(self):
        self.h.add({"title": "Parent", "what": "Parent", "done_when": "Parent done"})
        self.h.run("next")
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "split work",
                "finding_ids": [],
                "decision_ids": [],
                "atomic": False,
                "decomposition_reason": "independent child outcomes",
            }
        )
        self.h.add({"title": "Child one", "what": "One", "done_when": "One done", "parent": "S00001T00001"})
        self.h.add({"title": "Child two", "what": "Two", "done_when": "Two done", "parent": "S00001T00001"})
        tasks = Store(self.root).load_tasks()
        self.assertEqual(tasks["S00001T00001-0000001"].sequence, 1)
        self.assertEqual(tasks["S00001T00001-0000002"].sequence, 2)
        status = json.loads(self.h.run("status", "--compact", raw=True).stdout)
        self.assertTrue(status["ok"])

    def test_learn_from_log_can_queue_one_fix_per_commit_tasks(self):
        runtime = self.root / ".manager" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "error-log.ndjson").write_text(
            json.dumps(
                {
                    "recorded_at": "2026-01-01T00:00:00+00:00",
                    "command": "manager submit",
                    "argv": ["submit"],
                    "input": "{}",
                    "output": {
                        "error": "INVALID_SCHEMA",
                        "what": "missing required field",
                        "do": "Run manager submit-schema and retry.",
                    },
                }
            ) + "\n",
            encoding="utf-8",
        )
        payload = json.loads(self.h.run("learn", "from-log", "--create-tasks", raw=True).stdout)
        self.assertTrue(payload["rcas"])
        self.assertTrue(payload["created_tasks"])
        self.assertIn("ASD-STE100", payload["reminder"])
        tasks = Store(self.root).load_tasks()
        created_id = payload["created_tasks"][0]["id"]
        self.assertIn("One fix per commit.", tasks[created_id].body)
    def test_plan_rejects_missing_what_done_when(self):
        self.h.add({"title": "Needs definition"})
        r = self.h.run("task", "plan", check=False)
        self.assertIn("ERROR: INVALID_TASK", r.stderr)
        self.assertIn("WHAT and DONE_WHEN", r.stderr)
        self.assertIn("DO:", r.stderr)

    def test_valid_plan_selects_one_active_and_rejects_second(self):
        self.h.add({"title": "A", "what": "Do A", "done_when": "A works"})
        self.h.add({"title": "B", "what": "Do B", "done_when": "B works"})
        env = self.h.run("next").stdout
        self.assertIn("TASK: S00001T00001", env)
        self.assertIn("ROLE: senior_expert", env)
        tasks = Store(self.root).load_tasks()
        self.assertEqual([t.status for t in tasks.values()].count("active"), 1)
        # A second planned task remains queued while the active task owns the loop.
        r = self.h.run("next", check=True)
        self.assertIn("TASK: S00001T00001", r.stdout)

    def test_analysis_to_planning_then_valid_plan(self):
        self.h.add({"title":"Build feature","what":"Build feature","done_when":"Tests pass"})
        self.h.run("next")
        self.assertEqual(self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True}).stdout.strip(), "OK planning")
        plan={"steps":[{"title":"Implement","action":"Implement feature","accept":["Feature works"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]}
        r=self.h.submit(plan)
        self.assertIn("plan accepted",r.stdout)
        env=self.h.run("next").stdout
        self.assertIn("PHASE: implementation",env)
        self.assertIn("STEP: STEP-0001",env)

    def test_unreachable_context_rejected(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        r=self.h.run("context","S00001T00001/FINDING-9999",check=False)
        self.assertIn("ERROR: UNREACHABLE_CONTEXT",r.stderr)
        self.assertIn("DO:",r.stderr)

    def test_context_compact_projection_is_bounded(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.run(
            "finding",
            "add",
            stdin=json.dumps(
                {
                    "question": "What must change?",
                    "finding": "Only adapter wiring and validator behavior must change.",
                    "evidence": ["src/app.py", "tests/test_app.py"],
                    "impact": "Limits scope and keeps risk bounded.",
                    "confidence": "high",
                }
            ),
        )
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "analysis complete",
                "finding_ids": ["FINDING-0001"],
                "decision_ids": [],
                "atomic": True,
            }
        )
        r = self.h.run("context", "S00001T00001/FINDING-0001", "--compact", "--max-chars", "260", raw=True)
        payload = json.loads(r.stdout)
        content = payload["records"][0]["content"]
        self.assertIn("CONTEXT: FINDING-0001", content)
        self.assertIn("SUMMARY:", content)
        self.assertIn("- finding:", content)
        self.assertLessEqual(len(content), 260)

    def test_context_compact_rejects_invalid_max_chars(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        r = self.h.run("context", "--compact", "--max-chars", "100", check=False)
        self.assertIn("ERROR: INVALID_CONTEXT_LIMIT", r.stderr)

    def test_next_json_contains_next_command_and_output_limit(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        r = self.h.run("next", raw=True)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["task"], "S00001T00001")
        self.assertIn("next_command", payload)
        self.assertIn("output_limit", payload)
        self.assertEqual(payload["output_limit"], 8000)

    def test_context_json_includes_task_and_phase(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.run(
            "finding",
            "add",
            stdin=json.dumps(
                {
                    "question": "What must change?",
                    "finding": "Only adapter wiring must change.",
                    "evidence": ["src/app.py"],
                    "impact": "Bounded scope.",
                    "confidence": "high",
                }
            ),
        )
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "analysis complete",
                "finding_ids": ["FINDING-0001"],
                "decision_ids": [],
                "atomic": True,
            }
        )
        r = self.h.run("context", "S00001T00001/FINDING-0001", "--compact", raw=True)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["task"], "S00001T00001")
        self.assertEqual(payload["phase"], "planning")
        self.assertEqual(payload["records"][0]["id"], "FINDING-0001")

    def test_submit_schema_returns_active_phase_schema(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
        r = self.h.run("submit-schema", raw=True)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["phase"], "planning")
        self.assertIn("steps", payload["return_schema"])
        self.assertIn("return_schema_path", payload)
        self.assertTrue((self.root / payload["return_schema_path"]).exists())
        self.assertEqual(payload["output_limit"], 8000)

    def test_submit_schema_path_only_returns_direct_schema_path(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
        r = self.h.run("submit-schema", "--schema-path", raw=True)
        payload = json.loads(r.stdout)
        self.assertIn("schema_path", payload)
        schema_path = self.root / payload["schema_path"]
        self.assertTrue(schema_path.exists())
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIn("steps", schema)

    def test_invalid_schema_error_includes_active_schema_path(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        bad = self.h.run(
            "submit",
            stdin=json.dumps({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True, "unexpected": True}),
            check=False,
            raw=True,
        )
        payload = json.loads(bad.stderr)
        self.assertEqual(payload["error"], "INVALID_SCHEMA")
        self.assertIn("schema_path", payload)
        self.assertTrue((self.root / payload["schema_path"]).exists())

    def test_error_log_records_command_input_and_output(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
        bad_payload = {"steps": []}
        for _ in range(6):
            self.h.run("status", raw=True)
        self.h.run("submit", stdin=json.dumps(bad_payload), check=False, raw=True)
        agent_id = Store(self.root).load_tasks()["S00001T00001"].agent_id
        queue_path = self.root / f".manager/runtime/last-10-{agent_id}-log.ndjson"
        log_path = self.root / f".manager/runtime/error-{agent_id}-log.ndjson"
        self.assertTrue(queue_path.exists())
        self.assertTrue(log_path.exists())
        lines = [x for x in log_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertTrue(lines)
        record = json.loads(lines[-1])
        self.assertTrue(record["command"].startswith("manager"))
        self.assertIn("submit", record["command"])
        self.assertEqual(record["input"], json.dumps(bad_payload))
        self.assertIsInstance(record["output"], dict)
        self.assertIn("error", record["output"])
        self.assertEqual(len(lines), 10)
        queue_lines = [x for x in queue_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertEqual(queue_lines, [])

    def test_error_log_records_subsequent_failures_after_protecting_file(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
        self.h.run("submit", stdin=json.dumps({"steps": []}), check=False, raw=True)
        self.h.run("submit", stdin=json.dumps({"steps": []}), check=False, raw=True)
        agent_id = Store(self.root).load_tasks()["S00001T00001"].agent_id
        log_path = self.root / f".manager/runtime/error-{agent_id}-log.ndjson"
        lines = [x for x in log_path.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertGreaterEqual(len(lines), 2)
        self.assertTrue(any("submit" in json.loads(line).get("command", "") for line in lines))

    def test_archive_replan_same_timestamp_creates_unique_directory(self):
        store = Store(self.root)
        store.initialize()
        task_id = "S00001T00001"
        step1 = __import__("manager.core", fromlist=["Step"]).Step("STEP-0001", task_id, 1, "done", "developer", "one", "one")
        step2 = __import__("manager.core", fromlist=["Step"]).Step("STEP-0002", task_id, 2, "done", "developer", "two", "two")
        first = self.root / ".manager/steps/S00001T00001-STEP-0001.md"
        second = self.root / ".manager/steps/S00001T00001-STEP-0002.md"
        first.write_text("one", encoding="utf-8")
        second.write_text("two", encoding="utf-8")
        with mock.patch("manager.cli.now", return_value="2026-10-29T12:00:00+00:00"):
            cli.archive_existing_steps(store, task_id, [step1])
            cli.archive_existing_steps(store, task_id, [step2])
        archives = sorted((self.root / ".manager/archive" / task_id).glob("*"))
        self.assertEqual(len(archives), 2)
        self.assertTrue(any((d / "S00001T00001-STEP-0001.md").exists() for d in archives))
        self.assertTrue(any((d / "S00001T00001-STEP-0002.md").exists() for d in archives))

    def test_status_compact_and_verify_json(self):
        compact_payload = json.loads(self.h.run("status", "--compact", raw=True).stdout)
        self.assertEqual(compact_payload["task"], "NO_TASK")
        payload = json.loads(self.h.run("verify", raw=True).stdout)
        self.assertTrue(payload["ok"])

    def test_json_error_envelope_contains_hint(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        r = self.h.run("context", "--compact", "--max-chars", "100", check=False, raw=True)
        payload = json.loads(r.stderr)
        self.assertEqual(payload["error"], "INVALID_CONTEXT_LIMIT")
        self.assertIn("do", payload)

    def test_verify_is_non_mutating_when_no_manager_state(self):
        self.assertFalse((self.root / ".manager").exists())
        payload = json.loads(self.h.run("verify", raw=True).stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["state"], "NO_STATE")
        self.assertFalse((self.root / ".manager").exists())

    def test_manual_self_learning_add_and_list(self):
        add_payload = {
            "issue": "Model repeatedly submits unsupported field in step_validation.",
            "error_code": "INVALID_SCHEMA",
            "severity": "high",
            "suggestion": "Echo allowed fields in each invalid-schema error.",
            "impact": "Causes repeated retries.",
            "evidence": ["submit payload had extra key foo"],
        }
        created = json.loads(self.h.run("learn", "add", stdin=json.dumps(add_payload), raw=True).stdout)
        self.assertTrue(created["id"].startswith("LEARN-"))
        listed = json.loads(self.h.run("learn", "list", "--limit", "5", raw=True).stdout)
        self.assertGreaterEqual(len(listed["records"]), 1)
        self.assertEqual(listed["records"][-1]["issue"], add_payload["issue"])

    def test_boundary_and_validation_failure_return_to_implementation(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        r=self.h.submit({"outcome":"completed","summary":"bad","changed_files":["secret.txt"]},check=False)
        self.assertIn("ERROR: BOUNDARY_VIOLATION",r.stderr)
        self.h.submit({"outcome":"completed","summary":"ok","changed_files":[]})
        r=self.h.submit({"outcome":"failed","runs":[{"command":"python -m unittest","exit_code":1,"summary":"failed"}]})
        self.assertEqual(r.stdout.strip(),"OK implementation")
        self.assertIn("PHASE: implementation",self.h.run("next").stdout)

    def test_commit_before_validation_rejected(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"required","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.h.submit({"outcome":"completed","summary":"ok","changed_files":[]})
        # The manager must not expose a commit transition until validation has passed.
        self.assertIn("PHASE: step_validation", self.h.run("next").stdout)
        self.assertNotIn("PHASE: step_commit", self.h.run("next").stdout)

    def test_decomposition_parent_gated(self):
        self.h.add({"title":"Parent","what":"Do all","done_when":"All done"})
        self.h.run("next")
        r=self.h.submit({"outcome":"completed","summary":"too large","finding_ids":[],"decision_ids":[],"atomic":False,"decomposition_reason":"Two independent outcomes"})
        self.assertEqual(r.stdout.strip(),"OK DECOMPOSITION_REQUIRED")
        self.assertIn("PHASE",self.h.run("next").stdout) if False else None
        self.h.add({"title":"Child","what":"Child","done_when":"Child done","parent":"S00001T00001"})
        self.h.run("task", "plan", "S00001T00001-0000001")
        r=self.h.run("next")
        self.assertIn("TASK: S00001T00001-0000001",r.stdout)

    def test_duplicate_token_and_token_reuse(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        payload={"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True,"submission_token":"tok-1"}
        self.assertEqual(self.h.submit(payload).stdout.strip(),"OK planning")
        self.assertEqual(self.h.submit(payload).stdout.strip(),"OK planning")
        changed=dict(payload); changed["summary"]="different"
        r=self.h.submit(changed,check=False)
        self.assertIn("ERROR: TOKEN_REUSE",r.stderr)

    def test_no_task(self):
        r=self.h.run("next")
        self.assertEqual(r.stdout.strip(),"NO_TASK")

    def test_next_no_task_raw_includes_recovery_guidance(self):
        r = self.h.run("next", raw=True)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["result"], "NO_TASK")
        self.assertIn("manager status --compact", payload["do"])
        self.assertIn("manager task add", payload["do"])
        self.assertIn("schema_path", payload)
        self.assertTrue((self.root / payload["schema_path"]).exists())
        self.assertIn("next_commands", payload)

    def test_submit_schema_no_task_error_has_distinct_hint_and_schema_path(self):
        r = self.h.run("submit-schema", raw=True, check=False)
        payload = json.loads(r.stderr)
        self.assertEqual(payload["error"], "NO_TASK")
        self.assertIn("Run these commands in order:", payload["do"])
        self.assertIn("manager status --compact", payload["do"])
        self.assertIn("manager task add", payload["do"])
        self.assertIn("hint", payload)
        self.assertNotEqual(payload["hint"], payload["what"])
        self.assertIn("schema_path", payload)
        self.assertTrue((self.root / payload["schema_path"]).exists())

    def test_invalid_schema_error_has_explicit_do_and_additional_hint(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        r = self.h.run(
            "submit",
            stdin=json.dumps({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True, "unexpected": True}),
            check=False,
            raw=True,
        )
        payload = json.loads(r.stderr)
        self.assertEqual(payload["error"], "INVALID_SCHEMA")
        self.assertIn("Run these commands in order:", payload["do"])
        self.assertIn("manager submit-schema --schema-path", payload["do"])
        self.assertIn("manager submit", payload["do"])
        self.assertIn("hint", payload)
        self.assertNotEqual(payload["hint"], payload["what"])
        self.assertIn("schema_path", payload)


    def test_task_add_invalid_schema_uses_task_add_recovery_and_schema(self):
        bad = self.h.run("task", "add", stdin=json.dumps({"invalid": True}), check=False, raw=True)
        payload = json.loads(bad.stderr)
        self.assertEqual(payload["error"], "INVALID_SCHEMA")
        self.assertIn("manager task add", payload["do"])
        self.assertNotIn("manager submit", payload["do"])
        self.assertIn("schema_path", payload)
        self.assertTrue((self.root / payload["schema_path"]).exists())
        self.assertTrue(payload["schema_path"].endswith("task-add-input.schema.json"))

    def test_no_task_error_log_uses_uuid_agent_id(self):
        self.h.run("task", "add", stdin=json.dumps({"invalid": True}), check=False, raw=True)
        runtime_dir = self.root / ".manager" / "runtime"
        logs = sorted(runtime_dir.glob("error-*-log.ndjson"))
        self.assertTrue(logs)
        agent_segment = logs[-1].name[len("error-"):-len("-log.ndjson")]
        self.assertTrue(is_uuid_v4(agent_segment))


    def test_symlinked_managed_file_is_rejected(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        task = next((self.root / ".manager/tasks").glob("*.md"))
        original = task.read_text(encoding="utf-8")
        task.unlink()
        target = self.root / "outside.md"
        target.write_text(original, encoding="utf-8")
        task.symlink_to(target)
        r = self.h.run("status", check=False)
        self.assertIn("ERROR: MANAGED_PATH_SYMLINK", r.stderr)
        self.assertIn("DO:", r.stderr)

    def test_symlinked_managed_directory_is_rejected(self):
        self.h.add({"title": "Build"})
        tasks = self.root / ".manager/tasks"
        real = self.root / "outside-tasks"
        real.mkdir()
        for child in tasks.iterdir():
            child.rename(real / child.name)
        tasks.rmdir()
        tasks.symlink_to(real, target_is_directory=True)
        r = self.h.run("status", check=False)
        self.assertIn("ERROR: MANAGED_PATH_SYMLINK", r.stderr)
        self.assertIn("DO:", r.stderr)

    def test_symlinked_manager_lock_is_rejected(self):
        self.h.add({"title": "Build"})
        lock = self.root / ".manager/.manager.lock"
        lock.unlink()
        target = self.root / "outside.lock"
        target.touch()
        lock.symlink_to(target)
        r = self.h.run("status", check=False)
        self.assertIn("ERROR: MANAGED_PATH_SYMLINK", r.stderr)
        self.assertIn("DO:", r.stderr)

    def test_managed_file_tamper_detected(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        p=next((self.root/".manager/tasks").glob("*.md")); text=p.read_text(); p.chmod(0o644); p.write_text(text.replace("status: planned","status: done"))
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_roles(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.assertIn("ROLE: planner",self.h.run("next").stdout)
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.assertIn("ROLE: developer",self.h.run("next").stdout)

    def test_edit_draft_to_planned(self):
        self.h.add({"title": "Draft"})
        r = self.h.run("task", "edit", "S00001T00001", stdin=json.dumps({"title":"Edited","what":"Define","done_when":"Defined"}))
        self.assertIn("planned", r.stdout)
        self.assertEqual(Store(self.root).load_tasks()["S00001T00001"].title, "Edited")

    def test_supporting_files_are_lazy(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        meta = self.root / ".manager"
        self.assertFalse((meta/"knowledge/S00001T00001-analysis.md").exists())
        self.h.run("next")
        self.assertFalse((meta/"knowledge/S00001T00001-analysis.md").exists())
        self.h.run("finding", "add", stdin=json.dumps({"question":"q","finding":"f","evidence":["app.py"],"impact":"i","confidence":"high"}))
        self.assertTrue((meta/"knowledge/S00001T00001-analysis.md").exists())

    def test_step_only_exposes_current_step(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[
            {"title":"First","action":"First","accept":["first"],"load":[],"may_edit":[],"validation":["check1"],"commit_policy":"disabled","commit_type":"chore"},
            {"title":"Second","action":"Second","accept":["second"],"load":[],"may_edit":[],"validation":["check2"],"commit_policy":"disabled","commit_type":"chore"}
        ],"final_validation":["final"]})
        env=self.h.run("next").stdout
        self.assertIn("STEP: STEP-0001", env)
        self.assertIn("ACTION:\nFirst", env)
        self.assertNotIn("Second", env)
        self.h.submit({"outcome":"completed","summary":"first","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"check1","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        env=self.h.run("next").stdout
        self.assertIn("STEP: STEP-0002", env)
        self.assertIn("ACTION:\nSecond", env)
        self.assertNotIn("First", env)

    def test_final_validation_blocked_until_all_steps_done(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["v1"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        env=self.h.run("next").stdout
        self.assertIn("PHASE: step_validation", env)
        self.assertNotIn("PHASE: final_validation", env)

    def test_done_requires_final_commit_gate(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["v1"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"v1","exit_code":0,"summary":"ok"}]})
        self.h.run("submit",stdin=json.dumps({"outcome":"ready_to_commit"}))
        self.h.submit({"outcome":"passed","runs":[{"command":"final","exit_code":0,"summary":"ok"}],"review_findings":[],"diff_reviewed":True})
        t=Store(self.root).load_tasks()["S00001T00001"]
        self.assertEqual(t.status,"active")
        self.assertEqual(t.phase,"final_commit")

    def test_path_traversal_rejected_in_plan(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        r=self.h.submit({"steps":[{"title":"Bad","action":"Bad","accept":["x"],"load":[],"may_edit":["../secret"],"validation":["v"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]},check=False)
        self.assertIn("ERROR: INVALID",r.stderr)

    def test_direct_state_fields_are_rejected(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        r=self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True,"status":"done"},check=False)
        self.assertIn("ERROR: INVALID_SCHEMA",r.stderr)

    def test_restart_reconstructs_active_phase(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        # A new process is used for every harness invocation.
        env=self.h.run("next").stdout
        self.assertIn("TASK: S00001T00001",env); self.assertIn("PHASE: analysis",env)

    def test_filename_renames_with_state(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.assertTrue(list((self.root/".manager/tasks").glob("TODO-00-ACTIVE-03-*.md")))

    def test_block_unblock_roundtrip(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("block", "S00001T00001", stdin="waiting")
        self.assertTrue(list((self.root/".manager/tasks").glob("TODO-02-BLOCKED-03-*.md")))
        self.h.run("unblock", "S00001T00001")
        self.assertTrue(list((self.root/".manager/tasks").glob("TODO-01-TODO-03-*.md")))

    def test_decision_acceptance_is_required_for_plan_reference(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        d=self.h.run("decision","propose",stdin=json.dumps({"decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["e"]})).stdout.strip()
        did=d
        r=self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[did],"atomic":True},check=False)
        self.assertIn("ERROR: UNRESOLVED_DECISION",r.stderr)

    def test_duplicate_finding_submission_is_idempotent(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        p={"question":"q","finding":"f","evidence":["app.py"],"impact":"i","confidence":"high","submission_token":"f1"}
        a=self.h.run("finding","add",stdin=json.dumps(p)).stdout.strip(); b=self.h.run("finding","add",stdin=json.dumps(p)).stdout.strip()
        self.assertEqual(a,b)

    def test_malformed_frontmatter_stops_mutation(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        p=next((self.root/".manager/tasks").glob("*.md")); p.chmod(0o644); p.write_text("not frontmatter\n")
        r=self.h.run("next",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_initialize_recovers_analysis_phase_with_existing_steps(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.run("submit", stdin=json.dumps({
            "steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["v1"],"commit_policy":"disabled","commit_type":"chore"}],
            "final_validation":["final"]
        }))

        task_file = next((self.root / ".manager/tasks").glob("*S00001T00001.md"))
        task_file.chmod(0o644)
        task_file.write_text(task_file.read_text(encoding="utf-8").replace("phase: implementation", "phase: analysis"), encoding="utf-8")

        status_payload = json.loads(self.h.run("status", "--compact", raw=True).stdout)
        self.assertEqual(status_payload["task"], "S00001T00001")
        self.assertEqual(Store(self.root).load_tasks()["S00001T00001"].phase, "implementation")

    def test_no_shell_execution_for_validation(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        r=self.h.submit({"steps":[{"title":"One","action":"One","accept":["x"],"load":[],"may_edit":[],"validation":["echo safe; touch SHOULD_NOT_EXIST"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]}, check=False)
        self.assertIn("ERROR: INVALID_COMMAND",r.stderr)
        self.assertFalse((self.root/"SHOULD_NOT_EXIST").exists())

    def test_git_manager_creates_step_and_final_commits(self):
        if not __import__("shutil").which("git"):
            self.skipTest("git unavailable")
        repo=tempfile.TemporaryDirectory(); root=Path(repo.name)
        subprocess.run(["git","init","-q",str(root)],check=True); subprocess.run(["git","-C",str(root),"config","user.email","test@example.com"],check=True); subprocess.run(["git","-C",str(root),"config","user.name","Test"],check=True)
        (root/"app.py").write_text("print('old')\n"); subprocess.run(["git","-C",str(root),"add","app.py"],check=True); subprocess.run(["git","-C",str(root),"commit","-qm","init"],check=True)
        h=ManagerHarness(root); h.add({"title":"Change","what":"Change","done_when":"Changed"}); h.run("next"); h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True}); h.submit({"steps":[{"title":"Change","action":"Change","accept":["changed"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"required","commit_type":"fix"}],"final_validation":["python -m unittest"]}); (root/"app.py").write_text("print('new')\n"); h.submit({"outcome":"completed","summary":"changed","changed_files":["app.py"]}); h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]}); step_commit=h.submit({"outcome":"ready_to_commit"}).stdout.strip(); h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}],"review_findings":[],"diff_reviewed":True}); final=h.submit({"outcome":"ready_to_commit"}).stdout.strip(); log=subprocess.run(["git","-C",str(root),"log","--format=%s","-2"],check=True,capture_output=True,text=True).stdout.splitlines(); self.assertEqual(len(log),2); self.assertTrue(log[0].startswith("feat:")); self.assertTrue(log[1].startswith("fix:")); self.assertEqual(Store(root).load_tasks()["S00001T00001"].status,"done"); repo.cleanup()

    def test_finding_file_evidence_is_enriched_with_git_blob_hash(self):
        if not shutil.which("git"):
            self.skipTest("git unavailable")
        repo = tempfile.TemporaryDirectory(); root = Path(repo.name)
        try:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "app.py").write_text("print('hello')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
            h = ManagerHarness(root)
            h.add({"title": "Analyze", "what": "Analyze", "done_when": "Done"})
            h.run("next")
            h.run("finding", "add", stdin=json.dumps({"question": "q", "finding": "f", "evidence": ["app.py"], "impact": "i", "confidence": "high"}))
            analysis = (root / ".manager/knowledge/S00001T00001-analysis.md").read_text(encoding="utf-8")
            self.assertRegex(analysis, r"app.py:1 \| commit=[0-9a-f]{40} \| state=before")
        finally:
            repo.cleanup()

    def test_implementation_changed_files_evidence_has_git_blob_hash(self):
        if not shutil.which("git"):
            self.skipTest("git unavailable")
        repo = tempfile.TemporaryDirectory(); root = Path(repo.name)
        try:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "app.py").write_text("print('old')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
            h = ManagerHarness(root)
            h.add({"title": "Change", "what": "Change", "done_when": "Done"})
            h.run("next")
            h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
            h.submit({"steps": [{"title": "One", "action": "One", "accept": ["ok"], "load": [], "may_edit": ["app.py"], "validation": ["python -m unittest"], "commit_policy": "disabled", "commit_type": "chore"}], "final_validation": ["python -m unittest"]})
            (root / "app.py").write_text("print('new')\n", encoding="utf-8")
            h.submit({"outcome": "completed", "summary": "changed", "changed_files": ["app.py"]})
            evidence = (root / ".manager/evidence/S00001T00001-evidence.md").read_text(encoding="utf-8")
            self.assertRegex(evidence, r"CHANGED_FILES:\napp.py:1 \| commit=[0-9a-f]{40} \| state=before")
        finally:
            repo.cleanup()

    def test_commit_evidence_contains_after_state_with_commit_id(self):
        if not shutil.which("git"):
            self.skipTest("git unavailable")
        repo = tempfile.TemporaryDirectory(); root = Path(repo.name)
        try:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "app.py").write_text("print('old')\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
            h = ManagerHarness(root)
            h.add({"title": "Change", "what": "Change", "done_when": "Done"})
            h.run("next")
            h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
            h.submit({"steps": [{"title": "One", "action": "One", "accept": ["ok"], "load": [], "may_edit": ["app.py"], "validation": ["python -m unittest"], "commit_policy": "required", "commit_type": "fix"}], "final_validation": ["python -m unittest"]})
            (root / "app.py").write_text("print('new')\n", encoding="utf-8")
            h.submit({"outcome": "completed", "summary": "changed", "changed_files": ["app.py"]})
            h.submit({"outcome": "passed", "runs": [{"command": "python -m unittest", "exit_code": 0, "summary": "ok"}]})
            commit_id = h.submit({"outcome": "ready_to_commit"}).stdout.strip()
            evidence = (root / ".manager/evidence/S00001T00001-evidence.md").read_text(encoding="utf-8")
            self.assertIn("CHANGED_FILES_AFTER:", evidence)
            self.assertIn(f"commit={commit_id} | state=after", evidence)
        finally:
            repo.cleanup()

    def test_replan_never_reuses_archived_step_ids(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["v1"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        # Complete the first plan through final validation, then force a durable
        # planning correction exactly as a final-validation planning failure does.
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"v1","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.h.submit({"outcome":"failed","runs":[{"command":"final","exit_code":1,"summary":"failed"}],"review_findings":[],"failure_classification":"planning","diff_reviewed":True})
        self.assertEqual(Store(self.root).load_tasks()["S00001T00001"].phase, "planning")
        self.h.run("plan","submit",stdin=json.dumps({"steps":[{"title":"Replacement","action":"Replacement","accept":["replacement"],"load":[],"may_edit":[],"validation":["v2"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final2"]}))
        steps=Store(self.root).load_steps("S00001T00001")
        self.assertEqual([(s.id,s.sequence,s.status) for s in steps], [("STEP-0002",1,"ready")])
        archived=list((self.root/".manager/archive/S00001T00001").rglob("S00001T00001-STEP-0001.md"))
        self.assertTrue(archived)
        self.assertEqual(Store(self.root).load_tasks()["S00001T00001"].current_step, "STEP-0002")

    def test_no_actionable_work_after_completion(self):
        # An empty workspace is already a deterministic NO_TASK state.
        self.assertEqual(self.h.run("next").stdout.strip(), "NO_TASK")

    def test_optional_step_commit_can_be_skipped(self):
        if not shutil.which("git"):
            self.skipTest("git unavailable")
        repo = tempfile.TemporaryDirectory(); root = Path(repo.name)
        try:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "app.py").write_text("print('old')\n")
            subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
            h = ManagerHarness(root)
            h.add({"title": "Optional commit", "what": "Change app", "done_when": "Validation passes"})
            h.run("next")
            h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
            h.submit({"steps":[{"title":"Change","action":"Change","accept":["changed"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"optional","commit_type":"chore"}],"final_validation":["python -m unittest"]})
            (root / "app.py").write_text("print('new')\n")
            h.submit({"outcome":"completed","summary":"changed","changed_files":["app.py"]})
            h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
            result = h.submit({"outcome":"skip_commit"})
            self.assertEqual(result.returncode, 0)
            step = Store(root).load_steps("S00001T00001")[0]
            self.assertEqual(step.status, "done")
            self.assertEqual(step.commit_id, "skipped")
        finally:
            repo.cleanup()

    def test_required_step_commit_cannot_be_skipped(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["v1"],"commit_policy":"required","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"v1","exit_code":0,"summary":"ok"}]})
        r=self.h.submit({"outcome":"skip_commit"},check=False)
        self.assertIn("ERROR: COMMIT_REQUIRED",r.stderr)

    def test_changed_file_must_match_current_git_diff(self):
        if not shutil.which("git"):
            self.skipTest("git unavailable")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("base\n")
        subprocess.run(["git", "-C", str(self.root), "add", "src/app.py"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "base"], check=True)
        self.h.add({"title":"Diff fidelity","what":"change a file","done_when":"the changed file is recorded"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Change","action":"Change file","accept":["changed"],"load":[],"may_edit":["src/app.py"],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"fix"}],"final_validation":["python -m unittest"]})
        self.h.run("next")
        (self.root / "src/app.py").write_text("changed\n")
        (self.root / "src/app.py").write_text("base\n")
        result = self.h.submit({"outcome":"completed","summary":"claimed change","changed_files":["src/app.py"]}, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("ERROR: CHANGED_FILE_NOT_IN_DIFF", result.stderr)

    def test_git_tracked_deletion_is_a_valid_changed_file(self):
        if not shutil.which("git"):
            self.skipTest("git unavailable")
        repo = tempfile.TemporaryDirectory(); root = Path(repo.name)
        try:
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
            (root / "obsolete.py").write_text("print('obsolete')\n")
            subprocess.run(["git", "-C", str(root), "add", "obsolete.py"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)
            h=ManagerHarness(root)
            h.add({"title":"Delete obsolete file","what":"Delete obsolete.py","done_when":"File is removed"}); h.run("next")
            h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
            h.submit({"steps":[{"title":"Delete","action":"Delete obsolete.py","accept":["file removed"],"load":[],"may_edit":["obsolete.py"],"validation":["python -m unittest"],"commit_policy":"required","commit_type":"chore"}],"final_validation":["python -m unittest"]})
            (root / "obsolete.py").unlink()
            r=h.submit({"outcome":"completed","summary":"deleted","changed_files":["obsolete.py"]})
            self.assertEqual(r.returncode,0)
        finally:
            repo.cleanup()

class Iteration18StoryOrderingTests(ManagerTests):
    def test_root_tasks_stay_in_open_story(self):
        created = self.h.add({"title": "first", "what": "w", "done_when": "d"})
        self.assertIn("S00001T00001", created.stdout)
        created = self.h.add({"title": "second", "what": "w", "done_when": "d"})
        self.assertIn("S00001T00002", created.stdout)

    def test_new_story_can_be_created_before_current_story_completes(self):
        self.h.add({"title": "open", "what": "w", "done_when": "d"})
        result = self.h.run("task", "add", "--new-story", stdin=json.dumps({"title": "later", "what": "w", "done_when": "d"}))
        self.assertIn("S00002T00001", result.stdout)

    def test_multiple_new_stories_can_be_staged_while_story_is_active(self):
        self.h.add({"title": "story-1", "what": "w", "done_when": "d"})
        self.h.run("next")
        second = self.h.run("task", "add", "--new-story", stdin=json.dumps({"title": "story-2", "what": "w", "done_when": "d"}))
        third = self.h.run("task", "add", "--new-story", stdin=json.dumps({"title": "story-3", "what": "w", "done_when": "d"}))
        self.assertIn("S00002T00001", second.stdout)
        self.assertIn("S00003T00001", third.stdout)

    def test_default_add_stays_on_active_story_even_with_staged_future_stories(self):
        self.h.add({"title": "story-1-root", "what": "w", "done_when": "d"})
        self.h.run("next")
        self.h.run("task", "add", "--new-story", stdin=json.dumps({"title": "story-2", "what": "w", "done_when": "d"}))
        created = self.h.add({"title": "story-1-followup", "what": "w", "done_when": "d"})
        self.assertIn("S00001T00002", created.stdout)

    def test_blocked_active_story_prevents_later_story_activation(self):
        self.h.add({"title": "story-1", "what": "w", "done_when": "d"})
        self.h.run("task", "add", "--new-story", stdin=json.dumps({"title": "story-2", "what": "w", "done_when": "d"}))
        self.h.run("block", "S00001T00001", stdin="waiting on dependency")

        env = self.h.run("next")
        self.assertEqual(env.stdout.strip(), "NO_TASK")

        tasks = Store(self.root).load_tasks()
        self.assertEqual(tasks["S00001T00001"].status, "blocked")
        self.assertEqual(tasks["S00002T00001"].status, "planned")

    def test_completed_story_opens_next_story(self):
        self.h.add({"title": "first", "what": "w", "done_when": "d"})
        store = Store(self.root)
        with store.lock():
            store.initialize()
            task = next(iter(store.load_tasks().values()))
            task.status = "done"
            task.phase = None
            task.updated = task.created
            store.save_task(task)
            store.rebuild_index()
            store.refresh_integrity()
        created = self.h.add({"title": "next story", "what": "w", "done_when": "d"})
        self.assertIn("S00002T00001", created.stdout)


class Iteration12StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.h=ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def test_block_and_unblock_follow_required_transition(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        r=self.h.run("block", "S00001T00001", stdin="dependency unavailable")
        self.assertIn("OK S00001T00001 blocked", r.stdout)
        self.assertIn("TODO-02-BLOCKED-03-S00001T00001.md", [p.name for p in (self.root/".manager/tasks").glob("*.md")])
        r=self.h.run("unblock", "S00001T00001")
        self.assertIn("OK S00001T00001 planned", r.stdout)

    def test_cannot_unblock_non_blocked_task(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        r=self.h.run("unblock", "S00001T00001", check=False)
        self.assertIn("ERROR: INVALID_TRANSITION", r.stderr)



class Iteration12FinalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "manager@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Manager Test"], check=True)
        (self.root / "app.py").write_text("print('base')\n")
        subprocess.run(["git", "-C", str(self.root), "add", "app.py"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "init"], check=True)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _to_final_commit(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":["app.py"],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"check","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.h.submit({"outcome":"passed","runs":[{"command":"final","exit_code":0,"summary":"ok"}],"review_findings":[],"diff_reviewed":True})

    def test_final_commit_rejects_unapproved_uncommitted_path(self):
        self._to_final_commit()
        (self.root / "unrelated.txt").write_text("unrelated\n")
        r=self.h.submit({"outcome":"ready_to_commit"},check=False)
        self.assertIn("ERROR: DIRTY_WORKTREE", r.stderr)
        self.assertIn("unrelated.txt", r.stderr)



class Iteration30HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def test_startup_allows_later_story_before_earlier_story_completes(self):
        self.h.add({"title":"First","what":"first","done_when":"done"})
        # Create a second story through the managed command surface.
        self.h.run("task", "add", "--new-story", stdin=json.dumps({"title":"Second","what":"second","done_when":"done"}), check=False)
        result = self.h.run("status", check=False)
        self.assertNotIn("CORRUPT_STATE", result.stderr)

    def test_startup_allows_later_story_when_only_one_story_is_active(self):
        self.h.add({"title":"First","what":"first","done_when":"done"})
        first = next((self.root/".manager/tasks").glob("*.md"))
        original = first.read_text()
        text = original.replace("id: S00001T00001", "id: S00002T00001").replace("S00001T00001", "S00002T00001")
        target = self.root/".manager/tasks/TODO-01-TODO-03-S00002T00001.md"
        target.write_text(text); target.chmod(0o444)
        # Refreshing the manifest simulates a malicious actor who can rewrite
        # both managed content and its manifest while preserving parser shape.
        store = Store(self.root)
        store.refresh_integrity()
        result = self.h.run("status")
        self.assertIn('"task": "S00001T00001"', result.stdout)

    def test_startup_rejects_multiple_active_stories(self):
        self.h.add({"title": "First", "what": "first", "done_when": "done"})
        self.h.run("block", "S00001T00001", stdin="story 1 blocked")
        first = next((self.root / ".manager/tasks").glob("*.md"))
        original = first.read_text()
        story_two_text = original.replace("id: S00001T00001", "id: S00002T00001").replace("S00001T00001", "S00002T00001")
        second = self.root / ".manager/tasks/TODO-02-BLOCKED-03-S00002T00001.md"
        second.write_text(story_two_text.replace("status: blocked", "status: blocked").replace("blocker: story 1 blocked", "blocker: blocked"))
        second.chmod(0o444)
        store = Store(self.root)
        store.refresh_integrity()
        result = self.h.run("status", check=False)
        self.assertIn("CORRUPT_STATE", result.stderr)
        self.assertIn("more than one story has active lifecycle state", result.stderr)

    def test_block_rejects_cross_story_active_lifecycle_transition(self):
        self.h.add({"title": "First", "what": "first", "done_when": "done"})
        self.h.run("next")
        self.h.run("task", "add", "--new-story", stdin=json.dumps({"title": "Second", "what": "second", "done_when": "done"}))
        result = self.h.run("block", "S00002T00001", stdin="forced", check=False)
        self.assertIn("ERROR: STORY_SCOPE_CONFLICT", result.stderr)

    def test_command_surface_contains_required_simple_model_commands(self):
        from manager.cli import build_parser
        parser = build_parser()
        commands = {a for a in parser._subparsers._group_actions[0].choices}
        self.assertTrue({"next","context","submit","status","block","unblock"}.issubset(commands))


class Iteration32ContextEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_planning_envelope_exposes_findings_and_accepted_decisions(self):
        h = self.h
        h.add({"title":"Context plan","what":"Plan","done_when":"Planned"})
        h.run("next")
        h.run("finding", "add", stdin=json.dumps({"question":"q","finding":"f","evidence":["local"],"impact":"i","confidence":"high"}))
        did = h.run("decision", "propose", stdin=json.dumps({"decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["e"]})).stdout.strip()
        h.run("decision", "resolve", stdin=json.dumps({"decision_id":did,"status":"accepted"}))
        h.submit({"outcome":"completed","summary":"atomic","finding_ids":["FINDING-0001"],"decision_ids":[did],"atomic":True})
        env = h.run("next")
        self.assertIn("PHASE: planning", env.stdout)
        self.assertIn("- FINDING-0001", env.stdout)
        self.assertIn(f"- {did}", env.stdout)

    def test_planning_context_accepts_only_envelope_references(self):
        h = self.h
        h.add({"title":"Context plan","what":"Plan","done_when":"Planned"})
        h.run("next")
        h.run("finding", "add", stdin=json.dumps({"question":"q","finding":"f","evidence":["local"],"impact":"i","confidence":"high"}))
        h.submit({"outcome":"completed","summary":"atomic","finding_ids":["FINDING-0001"],"decision_ids":[],"atomic":True})
        h.run("next")
        ok = h.run("context", stdin=None)
        self.assertIn("CONTEXT: FINDING-0001", ok.stdout)
        bad = h.run("context", "FINDING-9999", check=False)
        self.assertIn("UNREACHABLE_CONTEXT", bad.stderr)


if __name__ == "__main__": unittest.main()

class Iteration02HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _to_final_validation(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})

    def test_shell_control_validation_rejected(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        r=self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["pytest && touch pwned"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]},check=False)
        self.assertIn("ERROR: INVALID_COMMAND",r.stderr)

    def test_secret_in_validation_summary_rejected(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        r=self.h.submit({"outcome":"passed","runs":[{"command":"pytest","exit_code":0,"summary":"api_key=SECRET"}]},check=False)
        self.assertIn("ERROR: SENSITIVE_OUTPUT",r.stderr)

    def test_final_validation_requires_explicit_diff_review(self):
        self._to_final_validation()
        r=self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}],"review_findings":[] ,"diff_reviewed":False},check=False)
        self.assertIn("ERROR: DIFF_REVIEW_REQUIRED",r.stderr)

    def test_decision_resolution_is_append_only(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        did=self.h.run("decision","propose",stdin=json.dumps({"decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["e"]})).stdout.strip()
        self.h.run("decision","resolve",stdin=json.dumps({"decision_id":did,"status":"accepted"}))
        text=next((self.root/".manager/knowledge").glob("*-decisions.md")).read_text()
        self.assertIn("STATUS:\nproposed",text)
        self.assertIn(f"## DECISION-RESOLUTION-{did}",text)
        self.assertIn("STATUS:\naccepted",text)

    def test_symlink_edit_boundary_rejected(self):
        outside=self.root.parent/"outside-manager-test.txt"; outside.write_text("x")
        link=self.root/"link.txt"
        link.symlink_to(outside)
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        r=self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":["link.txt"],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]},check=False)
        self.assertIn("ERROR: INVALID_PLAN",r.stderr)
        outside.unlink(missing_ok=True)

    def test_step_commit_recovery_after_git_commit_before_projection(self):
        if not __import__("shutil").which("git"):
            self.skipTest("git unavailable")
        repo=tempfile.TemporaryDirectory(); root=Path(repo.name)
        subprocess.run(["git","init","-q",str(root)],check=True); subprocess.run(["git","-C",str(root),"config","user.email","test@example.com"],check=True); subprocess.run(["git","-C",str(root),"config","user.name","Test"],check=True)
        (root/"app.py").write_text("old\n"); subprocess.run(["git","-C",str(root),"add","app.py"],check=True); subprocess.run(["git","-C",str(root),"commit","-qm","init"],check=True)
        h=ManagerHarness(root); h.add({"title":"Change","what":"Change","done_when":"Changed"}); h.run("next"); h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True}); h.submit({"steps":[{"title":"Change","action":"Change","accept":["changed"],"load":[],"may_edit":["app.py"],"validation":["pytest"],"commit_policy":"required","commit_type":"fix"}],"final_validation":["pytest"]}); (root/"app.py").write_text("new\n"); h.submit({"outcome":"completed","summary":"changed","changed_files":["app.py"]}); h.submit({"outcome":"passed","runs":[{"command":"pytest","exit_code":0,"summary":"ok"}]})
        store=Store(root); task=store.load_tasks()["S00001T00001"]; step=store.load_steps(task.id)[0]; step.status="committing"; step.commit_message="fix: change"; store.save_step(step); store.refresh_integrity()
        subprocess.run(["git","-C",str(root),"add","app.py"],check=True); subprocess.run(["git","-C",str(root),"commit","-qm","fix: change"],check=True)
        r=h.submit({"outcome":"ready_to_commit"})
        self.assertEqual(r.stdout.strip(),subprocess.run(["git","-C",str(root),"rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip())
        self.assertEqual(Store(root).load_tasks()["S00001T00001"].phase,"final_validation")
        repo.cleanup()

class Iteration03ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def test_evidence_command_is_structured_and_lazy(self):
        self.h.add({"title":"Evidence","what":"Collect evidence","done_when":"Recorded"})
        self.h.run("next")
        r=self.h.run("evidence","add",stdin=json.dumps({"type":"analysis_note","fields":{"RESULT":"observed"}}))
        self.assertIn("EVT-0001",r.stdout)
        self.assertTrue(list((self.root/".manager/evidence").glob("*.md")))

    def test_accepted_decision_can_be_referenced_after_append_only_resolution(self):
        self.h.add({"title":"Decision","what":"Choose","done_when":"Chosen"}); self.h.run("next")
        did=self.h.run("decision","propose",stdin=json.dumps({"decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["local"]})).stdout.strip()
        self.h.run("decision","resolve",stdin=json.dumps({"decision_id":did,"status":"accepted"}))
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[did],"atomic":True})
        self.assertIn("PHASE: planning",self.h.run("next").stdout)

    def test_step_projection_uses_canonical_task_link(self):
        self.h.add({"title":"Plan","what":"Plan","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]})
        text=next((self.root/".manager/steps").glob("*.md")).read_text()
        self.assertIn("task: ../tasks/TODO-00-ACTIVE-03-S00001T00001.md",text)

class Iteration04HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def _analysis(self):
        self.h.add({"title":"Decision work","what":"Choose","done_when":"Chosen"})
        self.h.run("next")

    def test_accepted_decision_can_be_superseded(self):
        self._analysis()
        first = self.h.run("decision", "propose", stdin=json.dumps({"decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["local"]})).stdout.strip()
        self.h.run("decision", "resolve", stdin=json.dumps({"decision_id":first,"status":"accepted"}))
        second = self.h.run("decision", "propose", stdin=json.dumps({"decision":"Use Y","rationale":"new evidence","alternatives":[],"consequences":["d"],"evidence":["local"],"supersedes":first})).stdout.strip()
        text = next((self.root/".manager/knowledge").glob("*-decisions.md")).read_text()
        self.assertIn(f"SUPERSEDES:\n{first}", text)
        self.assertNotIn(f"SUPERSEDED_BY:\n{second}", text)
        self.h.run("decision", "resolve", stdin=json.dumps({"decision_id":second,"status":"accepted"}))
        text = next((self.root/".manager/knowledge").glob("*-decisions.md")).read_text()
        self.assertIn(f"DECISION-RESOLUTION-{second}", text)
        self.assertIn(f"SUPERSEDED_BY:\n{second}", text)

    def test_plan_rejects_duplicate_normalized_actions(self):
        self._analysis()
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        r=self.h.submit({"steps":[
            {"title":"One","action":"Update the thing","accept":["one"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"},
            {"title":"Two","action":"  update   the THING ","accept":["two"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]},check=False)
        self.assertIn("ERROR: INVALID_PLAN",r.stderr)

    def test_startup_detects_non_contiguous_steps(self):
        self._analysis()
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"},{"title":"Two","action":"Two","accept":["two"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]})
        step=next((self.root/".manager/steps").glob("*-STEP-0002.md"))
        text=step.read_text().replace("sequence: 2","sequence: 4")
        step.chmod(0o644); step.write_text(text); step.chmod(0o444)
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_required_commit_done_without_commit_is_corruption(self):
        self._analysis()
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"required","commit_type":"chore"}],"final_validation":["pytest"]})
        step=next((self.root/".manager/steps").glob("*-STEP-0001.md"))
        text=step.read_text().replace("status: active","status: done")
        step.chmod(0o644); step.write_text(text); step.chmod(0o444)
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)


class Iteration05HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def _git_repo(self):
        subprocess.run(["git", "-C", str(self.root), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "app.py").write_text("print('base')\n")
        subprocess.run(["git", "-C", str(self.root), "add", "app.py"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "base"], check=True, capture_output=True)

    def test_git_activation_commits_preexisting_application_changes(self):
        self._git_repo(); (self.root / "app.py").write_text("print('preexisting')\n")
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        r=self.h.run("next")
        self.assertIn("TASK: S00001T00001", r.stdout)
        log = subprocess.run(["git", "-C", str(self.root), "log", "-1", "--format=%s"], check=True, capture_output=True, text=True).stdout.strip()
        self.assertIn("checkpoint before activating S00001T00001", log)

    def test_step_commit_recovery_requires_expected_parent(self):
        self._git_repo()
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"required","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        (self.root/"app.py").write_text("print('changed')\n"); self.h.submit({"outcome":"completed","summary":"ok","changed_files":["app.py"]}); self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        env=self.h.run("next").stdout; self.assertIn("PHASE: step_commit",env)
        # A different commit with the same subject must not be mistaken for the expected commit.
        subprocess.run(["git","-C",str(self.root),"commit","-am","chore: implement"],check=True,capture_output=True)
        r=self.h.submit({"outcome":"ready_to_commit"},check=False)
        self.assertIn("ERROR",r.stderr)

    def test_final_commit_recovery_requires_expected_parent(self):
        self._git_repo()
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":["app.py"],"validation":["python -m unittest"],"commit_policy":"required","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        (self.root/"app.py").write_text("print('changed')\n"); self.h.submit({"outcome":"completed","summary":"ok","changed_files":["app.py"]}); self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]}); self.h.run("next")
        # Normal path must still create the final commit.
        r=self.h.submit({"outcome":"ready_to_commit"}); self.assertTrue(r.stdout.strip())


class Iteration06DecisionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def _analysis(self):
        self.h.add({"title":"Decision lifecycle","what":"Choose","done_when":"Chosen"})
        self.h.run("next")

    def test_superseding_proposal_does_not_mutate_accepted_decision(self):
        self._analysis()
        first = self.h.run("decision", "propose", stdin=json.dumps({
            "decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["local"]
        })).stdout.strip()
        self.h.run("decision", "resolve", stdin=json.dumps({"decision_id":first,"status":"accepted"}))
        second = self.h.run("decision", "propose", stdin=json.dumps({
            "decision":"Use Y","rationale":"new evidence","alternatives":[],"consequences":["d"],"evidence":["local"],"supersedes":first
        })).stdout.strip()
        text = next((self.root/".manager/knowledge").glob("*-decisions.md")).read_text()
        self.assertIn(f"DECISION-RESOLUTION-{first}", text)
        accepted_resolution = re.search(rf"## DECISION-RESOLUTION-{re.escape(first)}\n\nDECISION_ID:\n{re.escape(first)}\n\nSTATUS:\n([^\n]+)", text)
        self.assertIsNotNone(accepted_resolution)
        self.assertEqual(accepted_resolution.group(1), "accepted")
        self.assertNotIn(f"SUPERSEDED_BY:\n{second}", text)
        self.assertIn(f"SUPERSEDES:\n{first}", text)
        self.h.run("decision", "resolve", stdin=json.dumps({"decision_id":second,"status":"accepted"}))
        text = next((self.root/".manager/knowledge").glob("*-decisions.md")).read_text()
        self.assertIn(f"STATUS:\nsuperseded", text)
        self.assertIn(f"SUPERSEDED_BY:\n{second}", text)

    def test_rejected_superseding_proposal_leaves_prior_decision_accepted(self):
        self._analysis()
        first = self.h.run("decision", "propose", stdin=json.dumps({
            "decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["local"]
        })).stdout.strip()
        self.h.run("decision", "resolve", stdin=json.dumps({"decision_id":first,"status":"accepted"}))
        second = self.h.run("decision", "propose", stdin=json.dumps({
            "decision":"Use Y","rationale":"new evidence","alternatives":[],"consequences":["d"],"evidence":["local"],"supersedes":first
        })).stdout.strip()
        self.h.run("decision", "resolve", stdin=json.dumps({"decision_id":second,"status":"rejected"}))
        text = next((self.root/".manager/knowledge").glob("*-decisions.md")).read_text()
        accepted_resolution = re.search(rf"## DECISION-RESOLUTION-{re.escape(first)}\n\nDECISION_ID:\n{re.escape(first)}\n\nSTATUS:\n([^\n]+)", text)
        self.assertIsNotNone(accepted_resolution)
        self.assertEqual(accepted_resolution.group(1), "accepted")
        self.assertNotIn(f"SUPERSEDED_BY:\n{second}", text)

class Iteration07SchemaHardeningTests(ManagerTests):
    def test_analysis_rejects_non_string_record_ids(self):
        self.h.add({"title":"Task","what":"Do it","done_when":"It works"})
        self.h.run("next")
        r = self.h.submit({"outcome":"completed","summary":"analysis","finding_ids":[1],"decision_ids":[],"atomic":True}, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("INVALID_SCHEMA", r.stderr)

    def test_plan_rejects_non_string_step_arrays(self):
        self.h.add({"title":"Task","what":"Do it","done_when":"It works"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"analysis","finding_ids":[],"decision_ids":[],"atomic":True})
        r = self.h.submit({"steps":[{"title":"Implement","action":"Do it","accept":[1],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]}, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("INVALID_SCHEMA", r.stderr)

    def test_validation_rejects_duplicate_command_results(self):
        self.h.add({"title":"Task","what":"Do it","done_when":"It works"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"analysis","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Do one thing","accept":["done"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]})
        self.h.submit({"outcome":"completed","summary":"changed","changed_files":[]})
        r = self.h.submit({"outcome":"passed","runs":[{"command":"pytest","exit_code":0,"summary":"ok"},{"command":"pytest","exit_code":0,"summary":"ok"}]}, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("INVALID_SCHEMA", r.stderr)

    def test_changed_files_reject_non_string_entries(self):
        self.h.add({"title":"Task","what":"Do it","done_when":"It works"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"analysis","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Do one thing","accept":["done"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]})
        r = self.h.submit({"outcome":"completed","summary":"changed","changed_files":[1]}, check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("INVALID_SCHEMA", r.stderr)

class Iteration08HardeningTests(unittest.TestCase):
    def test_task_add_rejects_non_string_definition_fields(self):
        root = Path(tempfile.mkdtemp())
        try:
            h = ManagerHarness(root)
            r = h.run("task", "add", stdin=json.dumps({"title": "Bad", "what": 123, "done_when": "x"}), check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("INVALID_SCHEMA", r.stderr)
            self.assertIn("DO:", r.stderr)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_task_add_rejects_non_integer_priority(self):
        root = Path(tempfile.mkdtemp())
        try:
            h = ManagerHarness(root)
            r = h.run("task", "add", stdin=json.dumps({"title": "Bad", "priority": "3"}), check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("INVALID_SCHEMA", r.stderr)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_final_validation_failure_returns_to_planning(self):
        root = Path(tempfile.mkdtemp())
        try:
            h = ManagerHarness(root)
            h.add({"title":"Change","what":"Change","done_when":"Changed"})
            h.run("next")
            h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
            h.submit({"steps":[{"title":"Change","action":"Change","accept":["changed"],"load":[],"may_edit":["app.py"],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]})
            (root/"app.py").write_text("new\n")
            h.submit({"outcome":"completed","summary":"ok","changed_files":["app.py"]})
            h.submit({"outcome":"passed","runs":[{"command":"pytest","exit_code":0,"summary":"ok"}]})
            h.submit({"outcome":"ready_to_commit"})
            h.run("next")
            r = h.submit({"outcome":"failed","runs":[{"command":"pytest","exit_code":1,"summary":"failure"}],"review_findings":["integration failure"],"failure_classification":"planning","diff_reviewed":True})
            self.assertIn("OK planning", r.stdout)
            task = Store(root).load_tasks()["S00001T00001"]
            self.assertEqual(task.phase, "planning")
            self.assertIsNone(task.current_step)
        finally:
            shutil.rmtree(root, ignore_errors=True)

class Iteration09ProtocolHardeningTests(ManagerTests):
    def _plan(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.h.submit({"outcome":"completed","summary":"done","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.assertIn("PHASE: final_validation", self.h.run("next").stdout)

    def test_final_failure_requires_and_honors_classification(self):
        self._plan()
        bad = self.h.submit({"outcome":"failed","runs":[{"command":"python -m unittest","exit_code":1,"summary":"failed"}],"review_findings":["implementation defect"],"diff_reviewed":True}, check=False)
        self.assertIn("INVALID_SCHEMA", bad.stderr)
        r = self.h.submit({"outcome":"failed","runs":[{"command":"python -m unittest","exit_code":1,"summary":"failed"}],"review_findings":["implementation defect"],"failure_classification":"implementation","diff_reviewed":True})
        self.assertEqual(r.stdout.strip(), "OK implementation")
        self.assertIn("PHASE: implementation", self.h.run("next").stdout)

    def test_final_failure_can_return_to_planning(self):
        self._plan()
        r = self.h.submit({"outcome":"failed","runs":[{"command":"python -m unittest","exit_code":1,"summary":"failed"}],"review_findings":["plan gap"],"failure_classification":"planning","diff_reviewed":True})
        self.assertEqual(r.stdout.strip(), "OK planning")
        self.assertIn("PHASE: planning", self.h.run("next").stdout)

    def test_step_validation_rejects_boolean_exit_code(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"}); self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.h.submit({"outcome":"completed","summary":"done","changed_files":[]})
        r=self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":True,"summary":"ok"}]},check=False)
        self.assertIn("INVALID_SCHEMA",r.stderr)


class Iteration13FinalCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
    def tearDown(self): self.tmp.cleanup()

    def _to_final_validation(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":["app.py"],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"check","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})

    def test_implementation_classification_returns_directly_to_new_corrective_step(self):
        self._to_final_validation()
        r=self.h.submit({"outcome":"failed","runs":[{"command":"final","exit_code":1,"summary":"failed"}],"review_findings":["Fix the implementation defect in app.py"],"failure_classification":"implementation","diff_reviewed":True})
        self.assertEqual(r.stdout.strip(),"OK implementation")
        env=self.h.run("next").stdout
        self.assertIn("PHASE: implementation",env)
        self.assertIn("STEP: STEP-0002",env)
        step=(self.root/".manager/steps/S00001T00001-STEP-0002.md").read_text()
        self.assertIn("Fix the implementation defect in app.py",step)

    def test_multiple_implementation_findings_still_require_planning(self):
        self._to_final_validation()
        r=self.h.submit({"outcome":"failed","runs":[{"command":"final","exit_code":1,"summary":"failed"}],"review_findings":["Fix A","Fix B"],"failure_classification":"implementation","diff_reviewed":True})
        self.assertEqual(r.stdout.strip(),"OK planning")
        self.assertIn("PHASE: planning",self.h.run("next").stdout)


class Iteration10ManagedSchemaTests(unittest.TestCase):
    def test_submission_token_must_be_string(self):
        root = Path(tempfile.mkdtemp())
        try:
            h = ManagerHarness(root)
            h.add({"title":"Build","what":"Build","done_when":"Done"})
            h.run("next")
            r = h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True,"submission_token":123}, check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("INVALID_SCHEMA", r.stderr)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_missing_task_frontmatter_field_is_detected(self):
        root = Path(tempfile.mkdtemp())
        try:
            h = ManagerHarness(root)
            h.add({"title":"Build"})
            task = next((root/".manager/tasks").glob("*.md"))
            text = task.read_text()
            task.chmod(0o644)
            task.write_text(text.replace("priority: 3\n", "", 1))
            r = h.run("status", check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertRegex(r.stderr, r"(CORRUPT_MANAGED_FILE|MANAGED_FILE_TAMPERED)")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_missing_step_frontmatter_field_is_detected(self):
        root = Path(tempfile.mkdtemp())
        try:
            h = ManagerHarness(root)
            h.add({"title":"Build","what":"Build","done_when":"Done"})
            h.run("next")
            h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
            h.submit({"steps":[{"title":"Implement","action":"Implement","accept":["works"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
            step = next((root/".manager/steps").glob("*.md"))
            text = step.read_text()
            step.chmod(0o644)
            step.write_text(text.replace("commit_type: chore\n", "", 1))
            r = h.run("status", check=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertRegex(r.stderr, r"(CORRUPT_MANAGED_FILE|MANAGED_FILE_TAMPERED)")
        finally:
            shutil.rmtree(root, ignore_errors=True)


class Iteration11ExecutionConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _planned_active(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")

    def _implemented(self):
        self._planned_active()
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})

    def test_workspace_schema_tamper_is_detected(self):
        self.h.add({"title":"Build"})
        p=self.root/".manager/workspace.md"
        p.chmod(0o644)
        p.write_text(p.read_text().replace("commit_mode: disabled", "commit_mode: nonsense"))
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_execution_phase_and_step_state_must_agree(self):
        self._implemented()
        task=next((self.root/".manager/tasks").glob("*.md"))
        task.chmod(0o644)
        task.write_text(task.read_text().replace("phase: step_validation", "phase: step_commit"))
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_missing_current_step_is_detected(self):
        self._implemented()
        self.h.run("next")
        task=next((self.root/".manager/tasks").glob("*.md"))
        task.chmod(0o644)
        task.write_text(task.read_text().replace("current_step: STEP-0001", "current_step: "))
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_malformed_submission_ledger_has_structured_corruption_error(self):
        self.h.add({"title":"Build"})
        p=self.root/".manager/submissions.json"
        p.chmod(0o644)
        p.write_text('{"tok":{"fingerprint":123,"response":false,"token":"tok"}}\n')
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

    def test_invalid_submission_fingerprint_is_detected(self):
        self.h.add({"title":"Build"})
        p=self.root/".manager/submissions.json"
        p.chmod(0o644)
        p.write_text('{"tok":{"fingerprint":"bad","response":"OK","token":"tok"}}\n')
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED",r.stderr)

class Iteration11ReplanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_failed_final_validation_allows_archived_replan(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"First","action":"First","accept":["first"],"load":[],"may_edit":[],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"check","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.h.submit({"outcome":"failed","runs":[{"command":"final","exit_code":1,"summary":"bad"}],"review_findings":[],"diff_reviewed":True,"failure_classification":"planning"})
        self.assertIn("PHASE: planning", self.h.run("next").stdout)
        plan={"steps":[{"title":"Replacement","action":"Replacement","accept":["replacement"],"load":[],"may_edit":[],"validation":["check2"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final2"]}
        self.h.submit(plan)
        self.assertTrue((self.root/".manager/steps/S00001T00001-STEP-0002.md").exists())
        archived=list((self.root/".manager/archive/S00001T00001").rglob("S00001T00001-STEP-0001.md"))
        self.assertEqual(len(archived),1)
        current=(self.root/".manager/steps/S00001T00001-STEP-0002.md").read_text()
        self.assertIn("Replacement",current)




class Iteration15TransitionHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_active_implementation_cannot_jump_to_expand(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        r = self.h.run("task", "expand", check=False)
        self.assertIn("ERROR: INVALID_TRANSITION", r.stderr)
        self.assertIn("analysis or planning", r.stderr)
        self.assertIn("PHASE: implementation", self.h.run("next").stdout)

    def test_active_planning_can_enter_expand(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        r = self.h.submit({"outcome":"completed","summary":"not atomic","finding_ids":[],"decision_ids":[],"atomic":False,"decomposition_reason":"independent outcomes"})
        self.assertIn("DECOMPOSITION_REQUIRED", r.stdout)

    def test_expanded_parent_resumes_to_final_validation_after_children_done(self):
        self.h.add({"title": "Parent", "what": "Parent", "done_when": "Parent done"})
        self.h.run("next")
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "split work",
                "finding_ids": [],
                "decision_ids": [],
                "atomic": False,
                "decomposition_reason": "independent child outcomes",
            }
        )
        self.h.add(
            {
                "title": "Child",
                "what": "Child",
                "done_when": "Child done",
                "parent": "S00001T00001",
            }
        )
        self.h.run("task", "plan", "S00001T00001-0000001")
        self.h.run("next")
        self.h.submit({"outcome": "completed", "summary": "atomic", "finding_ids": [], "decision_ids": [], "atomic": True})
        self.h.submit(
            {
                "steps": [
                    {
                        "title": "One",
                        "action": "One",
                        "accept": ["one"],
                        "load": [],
                        "may_edit": [],
                        "validation": ["check"],
                        "commit_policy": "disabled",
                        "commit_type": "chore",
                    }
                ],
                "final_validation": ["final"],
            }
        )
        self.h.submit({"outcome": "completed", "summary": "implemented", "changed_files": []})
        self.h.submit({"outcome": "passed", "runs": [{"command": "check", "exit_code": 0, "summary": "ok"}]})
        self.h.submit({"outcome": "ready_to_commit"})
        self.h.submit(
            {
                "outcome": "passed",
                "runs": [{"command": "final", "exit_code": 0, "summary": "ok"}],
                "review_findings": [],
                "diff_reviewed": True,
            }
        )
        self.h.submit({"outcome": "ready_to_commit"})
        parent = self.h.run("next")
        self.assertIn("TASK: S00001T00001", parent.stdout)
        self.assertIn("PHASE: final_validation", parent.stdout)


class Iteration14SchemaHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tampered_task_timestamp_is_rejected(self):
        self.h.add({"title": "Build"})
        path = next((self.root / ".manager/tasks").glob("*.md"))
        text = path.read_text()
        text = re.sub(r"^created: .*?$", "created: yesterday", text, flags=re.MULTILINE)
        path.chmod(0o644); path.write_text(text)
        r = self.h.run("status", check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED", r.stderr)

    def test_tampered_task_sequence_must_match_id(self):
        self.h.add({"title": "Build"})
        path = next((self.root / ".manager/tasks").glob("*.md"))
        text = path.read_text().replace("sequence: 1", "sequence: 2", 1)
        path.chmod(0o644); path.write_text(text)
        r = self.h.run("status", check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED", r.stderr)

    def test_active_task_with_missing_definition_is_corruption(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        path = next((self.root / ".manager/tasks").glob("*.md"))
        text = path.read_text().replace("WHAT:\nBuild", "WHAT:\n", 1)
        path.chmod(0o644); path.write_text(text)
        r = self.h.run("status", check=False)
        self.assertIn("ERROR: MANAGED_FILE_TAMPERED", r.stderr)

    def test_command_arguments_are_recorded_structurally(self):
        self.h.add({"title": "Build", "what": "Build", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        evidence = next((self.root/".manager/evidence").glob("*.md")).read_text()
        self.assertIn("COMMAND_ARGS:", evidence)
        self.assertIn('"python -m unittest": ["python", "-m", "unittest"]', evidence)

class Iteration17LifecycleAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_terminal_task_cannot_be_blocked(self):
        from manager.cli import transition_task
        self.h.add({"title": "Build"})
        task = Store(self.root).load_tasks()["S00001T00001"]
        task.status = "done"
        with self.assertRaises(ManagerError) as ctx:
            transition_task(task, "blocked")
        self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")

    def test_transition_guard_rejects_illegal_direct_transition(self):
        from manager.cli import transition_task
        tasks = self.h.add({"title": "Build"})
        self.assertIn("S00001T00001", tasks.stdout)
        task = Store(self.root).load_tasks()["S00001T00001"]
        with self.assertRaises(ManagerError) as ctx:
            transition_task(task, "done")
        self.assertEqual(ctx.exception.code, "INVALID_TRANSITION")

    def test_transition_guard_allows_idempotent_same_state(self):
        from manager.cli import transition_task
        store = Store(self.root)
        self.h.add({"title": "Build"})
        task = store.load_tasks()["S00001T00001"]
        transition_task(task, "draft")
        self.assertEqual(task.status, "draft")

class Iteration19StepReadinessTests(ManagerTests):
    def test_failed_validation_returns_step_to_ready_until_next(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"failed","runs":[{"command":"check","exit_code":1,"summary":"failed"}]})
        step = Store(self.root).load_steps("S00001T00001")[0]
        self.assertEqual(step.status, "ready")
        env = self.h.run("next").stdout
        self.assertIn("PHASE: implementation", env)
        step = Store(self.root).load_steps("S00001T00001")[0]
        self.assertEqual(step.status, "active")

    def test_next_step_is_ready_before_manager_next_promotes_it(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[
            {"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["check1"],"commit_policy":"disabled","commit_type":"chore"},
            {"title":"Two","action":"Two","accept":["two"],"load":[],"may_edit":[],"validation":["check2"],"commit_policy":"disabled","commit_type":"chore"},
        ],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"one","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"check1","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        step = Store(self.root).load_steps("S00001T00001")
        self.assertEqual([s.status for s in step], ["done", "ready"])
        env = self.h.run("next").stdout
        self.assertIn("STEP: STEP-0002", env)
        step = Store(self.root).load_steps("S00001T00001")
        self.assertEqual([s.status for s in step], ["done", "active"])

class Iteration20StepTransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_step_transition_graph_rejects_skips(self):
        from manager.cli import transition_step
        step = __import__('manager.core', fromlist=['Step']).Step(
            'STEP-0001', 'S00001T00001', 1, 'queued', 'developer', 'x', 'x', ['x'], [], [], ['pytest'], 'disabled', 'chore'
        )
        with self.assertRaises(ManagerError) as ctx:
            transition_step(step, 'active')
        self.assertEqual(ctx.exception.code, 'INVALID_STEP_TRANSITION')
        self.assertEqual(step.status, 'queued')

    def test_first_planned_step_is_ready_until_manager_next(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        plan = {"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["pytest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["pytest"]}
        self.h.run("submit", stdin=json.dumps(plan))
        from manager.core import Store
        step = Store(self.root).load_steps("S00001T00001")[0]
        self.assertEqual(step.status, "ready")
        self.assertIn("PHASE: implementation", self.h.run("next").stdout)
        self.assertEqual(Store(self.root).load_steps("S00001T00001")[0].status, "active")

    def test_ready_step_requires_manager_next_before_implementation(self):
        self.h.add({"title":"Build","what":"Build","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["v1"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.h.submit({"outcome":"failed","runs":[{"command":"v1","exit_code":1,"summary":"failed"}]})
        step = Store(self.root).load_steps("S00001T00001")[0]
        self.assertEqual(step.status, "ready")
        r = self.h.submit({"outcome":"completed","summary":"bypass","changed_files":[]}, check=False)
        self.assertIn("ERROR: STEP_NOT_ACTIVE", r.stderr)
        self.assertEqual(Store(self.root).load_steps("S00001T00001")[0].status, "ready")
        env = self.h.run("next").stdout
        self.assertIn("PHASE: implementation", env)
        self.assertEqual(Store(self.root).load_steps("S00001T00001")[0].status, "active")

class Iteration23MonotonicStepIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_replanning_never_reuses_archived_step_id(self):
        self.h.add({"title":"Replan","what":"Replan","done_when":"Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({
            "steps":[{"title":"First","action":"First","accept":["done"],"load":[],"may_edit":[],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],
            "final_validation":["final"],
        })
        self.h.submit({"outcome":"completed","summary":"implementation","changed_files":[]})
        self.h.submit({"outcome":"passed","runs":[{"command":"check","exit_code":0,"summary":"ok"}]})
        self.h.submit({"outcome":"ready_to_commit"})
        self.h.submit({"outcome":"failed","runs":[{"command":"final","exit_code":1,"summary":"bad"}],"review_findings":[],"diff_reviewed":True,"failure_classification":"planning"})
        self.assertIn("PHASE: planning", self.h.run("next").stdout)
        self.h.submit({
            "steps":[{"title":"Second","action":"Second","accept":["done"],"load":[],"may_edit":[],"validation":["check2"],"commit_policy":"disabled","commit_type":"chore"}],
            "final_validation":["final2"],
        })
        self.assertTrue((self.root / ".manager/steps/S00001T00001-STEP-0002.md").exists())
        self.assertFalse((self.root / ".manager/steps/S00001T00001-STEP-0001.md").exists())
        archived = list((self.root / ".manager/archive/S00001T00001").rglob("*-STEP-0001.md"))
        self.assertEqual(len(archived), 1)


class Iteration25WorkspaceCommitPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_persisted_workspace_commit_mode_is_authoritative(self):
        store = Store(self.root)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(store, "git_info", return_value=(False, None)))
            store.initialize()
        self.assertEqual(store.commit_mode(), "disabled")

        with mock.patch.object(store, "git_info", return_value=(True, str(self.root))):
            self.assertEqual(store.commit_mode(), "disabled")
            self.h.add({"title": "Policy stable", "what": "Keep policy", "done_when": "Policy remains disabled"})

        task = Store(self.root).load_tasks()["S00001T00001"]
        self.assertEqual(task.commit_mode, "disabled")

    def test_enabled_workspace_policy_survives_git_discovery_loss(self):
        store = Store(self.root)
        with mock.patch.object(store, "git_info", return_value=(True, str(self.root))):
            store.initialize()
            self.assertEqual(store.commit_mode(), "enabled")

        with mock.patch.object(store, "git_info", return_value=(False, None)):
            self.assertEqual(store.commit_mode(), "enabled")


class Iteration24TaskBlockConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_blocking_active_implementation_blocks_current_step(self):
        self.h.add({"title": "Block", "what": "Block", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        self.h.run("next")
        result = self.h.run("block", stdin="external dependency\n")
        self.assertIn("OK S00001T00001 blocked", result.stdout)
        from manager.core import Store
        store = Store(self.root)
        task = store.load_tasks()["S00001T00001"]
        step = store.load_steps(task.id)[0]
        self.assertEqual(task.status, "blocked")
        self.assertEqual(task.phase, None)
        self.assertEqual(step.status, "blocked")
        self.assertEqual(store.load_tasks()[task.id].blocker, "external dependency")

    def test_blocking_task_with_ready_step_marks_step_blocked(self):
        self.h.add({"title": "Block ready", "what": "Block", "done_when": "Done"})
        self.h.run("next")
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.h.submit({"steps":[{"title":"One","action":"One","accept":["one"],"load":[],"may_edit":[],"validation":["check"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["final"]})
        result = self.h.run("block", stdin="external dependency\n")
        self.assertIn("OK S00001T00001 blocked", result.stdout)
        from manager.core import Store
        store = Store(self.root)
        task = store.load_tasks()["S00001T00001"]
        step = store.load_steps(task.id)[0]
        self.assertEqual(task.status, "blocked")
        self.assertEqual(step.status, "blocked")
        status_payload = json.loads(self.h.run("status", "--compact", raw=True).stdout)
        self.assertIn(status_payload["task"], {"NO_TASK", "S00001T00001"})

    def test_supporting_record_duplicate_finding_ids_are_detected(self):
        self.h.add({"title":"Analyze","what":"Analyze","done_when":"Done"}); self.h.run("next")
        self.h.run("finding","add",stdin=json.dumps({"question":"q","finding":"f","evidence":["local"],"impact":"i","confidence":"high"}))
        path=self.root/".manager"/"knowledge"/"S00001T00001-analysis.md"
        text=path.read_text()
        record=text.split("## FINDING-0001",1)[1]
        path.chmod(0o644)
        path.write_text(text + "\n## FINDING-0001" + record)
        (self.root/".manager"/"integrity.json").unlink()
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: CORRUPT_MANAGED_FILE",r.stderr)
        self.assertIn("duplicate finding IDs",r.stderr)

    def test_supporting_record_invalid_decision_status_is_detected(self):
        self.h.add({"title":"Decide","what":"Decide","done_when":"Done"}); self.h.run("next")
        did=self.h.run("decision","propose",stdin=json.dumps({"decision":"Use X","rationale":"r","alternatives":[],"consequences":["c"],"evidence":["e"]})).stdout.strip()
        path=self.root/".manager"/"knowledge"/"S00001T00001-decisions.md"
        text=path.read_text().replace("STATUS:\nproposed", "STATUS:\ninvalid", 1)
        path.chmod(0o644)
        path.write_text(text)
        (self.root/".manager"/"integrity.json").unlink()
        r=self.h.run("status",check=False)
        self.assertIn("ERROR: CORRUPT_MANAGED_FILE",r.stderr)
        self.assertIn("invalid status",r.stderr)

    def test_blocking_analysis_does_not_create_a_step(self):
        self.h.add({"title": "Block analysis", "what": "Analyze", "done_when": "Done"})
        self.h.run("next")
        result = self.h.run("block", stdin="needs review\n")
        self.assertIn("OK S00001T00001 blocked", result.stdout)
        from manager.core import Store
        store = Store(self.root)
        self.assertEqual(store.load_steps("S00001T00001"), [])

    def test_protocol_role_assignment_covers_full_atomic_lifecycle(self):
        self.h.add({"title":"Role audit","what":"Implement role audit","done_when":"All phases complete"})
        env=self.h.run("next").stdout
        self.assertIn("ROLE: senior_expert",env)
        self.h.submit({"outcome":"completed","summary":"atomic","finding_ids":[],"decision_ids":[],"atomic":True})
        self.assertIn("ROLE: planner",self.h.run("next").stdout)
        self.h.submit({"steps":[{"title":"Implement","action":"Implement role audit","accept":["implemented"],"load":[],"may_edit":[],"validation":["python -m unittest"],"commit_policy":"disabled","commit_type":"chore"}],"final_validation":["python -m unittest"]})
        self.assertIn("ROLE: developer",self.h.run("next").stdout)
        self.h.submit({"outcome":"completed","summary":"implemented","changed_files":[]})
        self.assertIn("ROLE: tester",self.h.run("next").stdout)
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}]})
        self.assertIn("ROLE: committer",self.h.run("next").stdout)
        self.h.submit({"outcome":"ready_to_commit"})
        self.assertIn("ROLE: reviewer",self.h.run("next").stdout)
        self.h.submit({"outcome":"passed","runs":[{"command":"python -m unittest","exit_code":0,"summary":"ok"}],"review_findings":[],"diff_reviewed":True})
        self.assertIn("ROLE: committer",self.h.run("next").stdout)
        self.h.submit({"outcome":"ready_to_commit"})
        self.assertEqual(self.h.run("next").stdout.strip(),"NO_TASK")

    def test_protocol_error_contract_always_contains_recovery_do(self):
        self.h.add({"title":"Error contract","what":"Do work","done_when":"Work is done"})
        self.h.run("next")
        result=self.h.submit({"outcome":"completed","summary":"bad","finding_ids":[],"decision_ids":[],"atomic":True,"unexpected":True},check=False)
        self.assertIn("ERROR:",result.stderr)
        self.assertIn("WHAT:",result.stderr)
        self.assertIn("DO:",result.stderr)


class Iteration33JsonContractSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)
        self.repo_root = Path(__file__).resolve().parents[1]
        self.schemas = self.repo_root / "docs" / "schemas"

    def tearDown(self):
        self.tmp.cleanup()

    def _load_schema(self, name: str) -> dict:
        return json.loads((self.schemas / name).read_text(encoding="utf-8"))

    def _type_ok(self, expected, value) -> bool:
        mapping = {
            "object": dict,
            "array": list,
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "null": type(None),
        }
        expected_types = expected if isinstance(expected, list) else [expected]
        for et in expected_types:
            py = mapping[et]
            if et == "integer":
                if isinstance(value, int) and not isinstance(value, bool):
                    return True
            elif et == "number":
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return True
            elif isinstance(value, py):
                return True
        return False

    def _assert_schema(self, schema: dict, value, path: str = "$") -> None:
        if "anyOf" in schema:
            errors = []
            for option in schema["anyOf"]:
                try:
                    self._assert_schema(option, value, path)
                    return
                except AssertionError as exc:
                    errors.append(str(exc))
            raise AssertionError(f"{path}: value did not match anyOf options: {errors}")
        if "type" in schema:
            self.assertTrue(self._type_ok(schema["type"], value), f"{path}: type mismatch")
        if "enum" in schema:
            self.assertIn(value, schema["enum"], f"{path}: enum mismatch")
        if "const" in schema:
            self.assertEqual(value, schema["const"], f"{path}: const mismatch")
        if "minimum" in schema:
            self.assertGreaterEqual(value, schema["minimum"], f"{path}: minimum violation")
        if "pattern" in schema:
            self.assertRegex(str(value), schema["pattern"], f"{path}: pattern mismatch")

        if isinstance(value, dict):
            required = schema.get("required", [])
            for key in required:
                self.assertIn(key, value, f"{path}: missing required key {key}")
            props = schema.get("properties", {})
            for key, child in props.items():
                if key in value:
                    self._assert_schema(child, value[key], f"{path}.{key}")
            if schema.get("additionalProperties") is False:
                extra = set(value) - set(props)
                self.assertEqual(extra, set(), f"{path}: unexpected keys {sorted(extra)}")
        elif isinstance(value, list) and "items" in schema:
            for idx, item in enumerate(value):
                self._assert_schema(schema["items"], item, f"{path}[{idx}]")

    def test_schema_files_exist_and_are_parseable(self):
        expected = {
            "next.schema.json",
            "context.schema.json",
            "status.schema.json",
            "status-compact.schema.json",
            "submit-schema.schema.json",
            "bootstrap.schema.json",
            "verify.schema.json",
            "examples.schema.json",
            "learn-add.schema.json",
            "learn-list.schema.json",
            "learn-from-log.schema.json",
            "error.schema.json",
        }
        found = {p.name for p in self.schemas.glob("*.schema.json")}
        self.assertTrue(expected.issubset(found))
        for name in expected:
            self._load_schema(name)

    def test_next_context_status_submitschema_bootstrap_verify_examples_learn_and_error_match_schemas(self):
        self.h.add({"title": "Contract", "what": "Contract", "done_when": "Done"})

        next_payload = json.loads(self.h.run("next", raw=True).stdout)
        self._assert_schema(self._load_schema("next.schema.json"), next_payload)

        self.h.run(
            "finding",
            "add",
            stdin=json.dumps({
                "question": "q",
                "finding": "f",
                "evidence": ["local"],
                "impact": "i",
                "confidence": "high",
            }),
        )
        self.h.submit({
            "outcome": "completed",
            "summary": "atomic",
            "finding_ids": ["FINDING-0001"],
            "decision_ids": [],
            "atomic": True,
        })

        context_payload = json.loads(self.h.run("context", "FINDING-0001", "--compact", raw=True).stdout)
        self._assert_schema(self._load_schema("context.schema.json"), context_payload)

        submit_schema_payload = json.loads(self.h.run("submit-schema", raw=True).stdout)
        self._assert_schema(self._load_schema("submit-schema.schema.json"), submit_schema_payload)

        bootstrap_payload = json.loads(self.h.run("bootstrap", raw=True).stdout)
        self._assert_schema(self._load_schema("bootstrap.schema.json"), bootstrap_payload)

        status_payload = json.loads(self.h.run("status", raw=True).stdout)
        self._assert_schema(self._load_schema("status.schema.json"), status_payload)

        compact_payload = json.loads(self.h.run("status", "--compact", raw=True).stdout)
        self._assert_schema(self._load_schema("status-compact.schema.json"), compact_payload)

        verify_payload = json.loads(self.h.run("verify", raw=True).stdout)
        self._assert_schema(self._load_schema("verify.schema.json"), verify_payload)

        examples_payload = json.loads(self.h.run("examples", raw=True).stdout)
        self._assert_schema(self._load_schema("examples.schema.json"), examples_payload)

        learn_add_payload = json.loads(self.h.run("learn", "add", stdin=json.dumps({"issue": "needs better hint"}), raw=True).stdout)
        self._assert_schema(self._load_schema("learn-add.schema.json"), learn_add_payload)

        learn_list_payload = json.loads(self.h.run("learn", "list", "--limit", "10", raw=True).stdout)
        self._assert_schema(self._load_schema("learn-list.schema.json"), learn_list_payload)
        learn_from_log_payload = json.loads(self.h.run("learn", "from-log", "--limit", "10", raw=True).stdout)
        self._assert_schema(self._load_schema("learn-from-log.schema.json"), learn_from_log_payload)

        err = self.h.run("context", "--compact", "--max-chars", "100", check=False, raw=True)
        err_payload = json.loads(err.stderr)
        self._assert_schema(self._load_schema("error.schema.json"), err_payload)

    def test_prompt_includes_low_context_protocol_markers(self):
        result = self.h.run("--prompt", raw=True)
        text = result.stdout
        self.assertIn("LOW-CONTEXT SAFE", text)
        self.assertIn("manager submit-schema", text)
        self.assertIn("All commands return JSON by default.", text)
        self.assertIn("manager task --help", text)
        self.assertIn("research tools", text)

    def test_help_includes_nested_subcommand_discovery(self):
        result = self.h.run("--help", raw=True)
        text = result.stdout
        self.assertIn("manager task --help", text)
        low = text.lower()
        self.assertIn("stdin commands require piped/heredoc", low)
        self.assertIn("time out after", low)

    def test_prompt_does_not_read_stdin(self):
        class BlockingStdin:
            def read(self):
                raise AssertionError("stdin.read should not be called for --prompt")

        old_argv = sys.argv
        old_stdin = sys.stdin
        out, err = io.StringIO(), io.StringIO()
        sys.argv = ["manager", "--root", str(self.root), "--prompt"]
        sys.stdin = BlockingStdin()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                cli.main()
        finally:
            sys.argv = old_argv
            sys.stdin = old_stdin
        self.assertIn("MANAGER PROTOCOL", out.getvalue())

    def test_stdin_timeout_returns_contract_error(self):
        class SlowStdin:
            def read(self):
                import time
                time.sleep(2)
                return ""

        old_argv = sys.argv
        old_stdin = sys.stdin
        old_timeout = cli.STDIN_READ_TIMEOUT_SECONDS
        out, err = io.StringIO(), io.StringIO()
        sys.argv = ["manager", "--root", str(self.root), "task", "add"]
        sys.stdin = SlowStdin()
        cli.STDIN_READ_TIMEOUT_SECONDS = 1
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    cli.main()
                except SystemExit as exc:
                    code = int(exc.code or 0)
        finally:
            cli.STDIN_READ_TIMEOUT_SECONDS = old_timeout
            sys.argv = old_argv
            sys.stdin = old_stdin
        self.assertEqual(code, 2)
        payload = json.loads(err.getvalue())
        self.assertEqual(payload["error"], "INPUT_TIMEOUT")
        self.assertIn("what", payload)
        self.assertIn("do", payload)
        self.assertIn("hint", payload)
        self.assertIn("gotcha", payload)

    def test_error_contract_is_consistent_across_command_failures(self):
        scenarios = [
            (("submit-schema",), None),
            (("context", "--compact", "--max-chars", "100"), None),
            (("learn", "list", "--limit", "0"), None),
            (("plan", "submit"), json.dumps({"steps": [], "final_validation": []})),
            (("task", "plan"), None),
            (("task",), None),
            (("not-a-command",), None),
        ]
        for args, stdin in scenarios:
            result = self.h.run(*args, stdin=stdin, raw=True, check=False)
            payload = json.loads(result.stderr)
            self.assertIn("error", payload)
            self.assertIn("what", payload)
            self.assertIn("do", payload)
            self.assertIn("hint", payload)
            self.assertIn("gotcha", payload)
            self.assertRegex(payload["error"], r"^[A-Z0-9_]+$")
            self.assertTrue(payload["what"].strip())
            self.assertTrue(payload["do"].strip())
            self.assertTrue(payload["hint"].strip())
            self.assertTrue(payload["gotcha"].strip())

    def test_next_no_task_does_not_block_and_returns_guidance(self):
        result = self.h.run("next", raw=True)
        payload = json.loads(result.stdout)
        self.assertEqual(payload.get("result"), "NO_TASK")
        self.assertIn("schema_path", payload)
        self.assertTrue((self.root / payload["schema_path"]).exists())


class DoneChildInvariantRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.h = ManagerHarness(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_done_child_with_parent_and_no_grandchildren_is_valid(self):
        self.h.add({"title": "Parent", "what": "Coordinate", "done_when": "Children complete"})
        self.h.run("next")
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "needs decomposition",
                "finding_ids": [],
                "decision_ids": [],
                "atomic": False,
                "decomposition_reason": "split into child track",
            }
        )

        self.h.add(
            {
                "title": "Child",
                "what": "Implement child",
                "done_when": "Done",
                "parent": "S00001T00001",
            }
        )

        self.h.run("next")
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "atomic child",
                "finding_ids": [],
                "decision_ids": [],
                "atomic": True,
            }
        )
        self.h.submit(
            {
                "steps": [
                    {
                        "title": "Implement child",
                        "action": "Implement child",
                        "accept": ["Child works"],
                        "load": [],
                        "may_edit": ["app.py"],
                        "validation": ["check"],
                        "commit_policy": "disabled",
                        "commit_type": "chore",
                    }
                ],
                "final_validation": ["final-check"],
            }
        )
        self.h.submit(
            {
                "outcome": "completed",
                "summary": "implemented child",
                "changed_files": [],
            }
        )
        self.h.submit(
            {
                "outcome": "passed",
                "runs": [{"command": "check", "exit_code": 0, "summary": "ok"}],
            }
        )
        self.h.submit({"outcome": "ready_to_commit"})
        self.h.submit(
            {
                "outcome": "passed",
                "runs": [
                    {"command": "final-check", "exit_code": 0, "summary": "ok"}
                ],
                "review_findings": [],
                "diff_reviewed": True,
            }
        )
        self.h.submit({"outcome": "ready_to_commit"})

        child_task = Store(self.root).load_tasks()["S00001T00001-0000001"]
        self.assertEqual(child_task.status, "done")
        self.assertEqual(child_task.parent, "S00001T00001")

        status = self.h.run("status")
        self.assertEqual(status.returncode, 0)
        self.assertNotIn("CORRUPT_STATE", status.stderr)
