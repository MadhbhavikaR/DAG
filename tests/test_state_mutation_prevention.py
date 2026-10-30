import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from manager.core import ManagerError, Store, now
from manager.task import Task


class ReadOnlyTaskLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = Store(self.root)
        self.store.initialize()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialize_does_not_recreate_deleted_integrity_protected_workspace(self):
        self.store.refresh_integrity()
        workspace = self.store.meta / "workspace.md"
        workspace.unlink()

        with self.assertRaises(ManagerError) as error:
            self.store.initialize()

        self.assertEqual(error.exception.code, "MANAGED_FILE_TAMPERED")
        self.assertFalse(workspace.exists())

    def test_malformed_integrity_manifest_is_rejected_without_traceback(self):
        self.store.refresh_integrity()
        manifest = self.store.meta / "integrity.json"
        manifest.chmod(0o644)
        manifest.write_text("[]\n", encoding="utf-8")

        with self.assertRaises(ManagerError) as error:
            self.store.initialize()

        self.assertEqual(error.exception.code, "CORRUPT_STATE")
        self.assertIn("integrity manifest", error.exception.what)

    def test_loading_task_normalizes_uuid_in_memory_without_rewriting_record(self):
        agent_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        task = Task(
            path=self.store.tasks_dir / "placeholder.md",
            id="S00001T00001",
            title="Read-only loading regression",
            parent=None,
            sequence=1,
            priority=3,
            status="draft",
            commit_mode="disabled",
            created=now(),
            updated=now(),
            agent_id=agent_id,
        )
        self.store.save_task(task)
        task_path = self.store.tasks_dir / task.filename

        noncanonical_id = agent_id.upper()
        self.assertNotEqual(noncanonical_id, agent_id)
        original = task_path.read_text(encoding="utf-8")
        task_path.write_text(
            original.replace(f"agent_id: {agent_id}", f"agent_id: {noncanonical_id}"),
            encoding="utf-8",
        )
        before = task_path.read_bytes()

        loaded = self.store.load_tasks(validate=False)

        self.assertEqual(loaded[task.id].agent_id, agent_id)
        self.assertEqual(task_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
