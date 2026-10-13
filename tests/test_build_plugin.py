"""Tests for the Calibre plugin archive builder."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "build_plugin.py"
SPEC = importlib.util.spec_from_file_location("build_plugin", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
build_plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_plugin)


class BuildPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.original_root = build_plugin.ROOT
        self.original_src = build_plugin.SRC
        build_plugin.ROOT = self.root
        build_plugin.SRC = self.root / "src"
        build_plugin.SRC.mkdir()
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "test-plugin-dev"\n',
            encoding="utf-8",
        )
        (self.root / "src" / "__init__.py").write_text(
            "class AnnasArchiveStore:\n    version = (1, 2, 3)\n",
            encoding="utf-8",
        )
        for name in build_plugin.REQUIRED_FILES:
            if name != "__init__.py":
                (self.root / "src" / name).write_text(f"fixture for {name}\n", encoding="utf-8")

    def tearDown(self):
        build_plugin.ROOT = self.original_root
        build_plugin.SRC = self.original_src
        self.temp_dir.cleanup()

    def test_reads_version_and_checks_metadata(self):
        self.assertEqual(build_plugin.read_version(), "1.2.3")

    def test_rejects_invalid_plugin_metadata_version(self):
        (self.root / "__init__.py").write_text(
            'class AnnasArchiveStore:\n    version = "9.9.9"\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "three-part integer tuple"):
            build_plugin.read_version()

    def test_archive_name_contains_branch_and_version(self):
        self.assertEqual(
            build_plugin.archive_path("1.2.3"),
            self.root / "dist" / "annas-archieve-callibre-plugin-v1.2.3.zip",
        )

    def test_build_writes_exact_required_files_at_archive_root(self):
        output = build_plugin.archive_path(build_plugin.read_version())
        build_plugin.build(output)
        with ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), set(build_plugin.REQUIRED_FILES))
            self.assertEqual(archive.testzip(), None)

    def test_release_version_overrides_only_packaged_metadata(self):
        output = build_plugin.archive_path("1.2.3")
        original_source = (self.root / "src" / "__init__.py").read_text(encoding="utf-8")
        build_plugin.build(output, version_override="1.2.3")
        with ZipFile(output) as archive:
            packaged = archive.read("__init__.py").decode("utf-8")
        self.assertIn("version = (1, 2, 3)", packaged)
        self.assertEqual((self.root / "__init__.py").read_text(encoding="utf-8"), original_source)

    def test_invalid_release_version_cannot_be_injected(self):
        with self.assertRaisesRegex(ValueError, "Release version must be MAJOR.MINOR.PATCH"):
            build_plugin.build(build_plugin.archive_path("bad"), version_override="bad")

    def test_check_rejects_unexpected_archive_members(self):
        output = build_plugin.archive_path(build_plugin.read_version())
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            for name in build_plugin.REQUIRED_FILES:
                archive.writestr(name, (self.root / "src" / name).read_bytes())
            archive.writestr("unexpected.txt", "not part of the plugin")
        with self.assertRaisesRegex(ValueError, "Unexpected ZIP entries"):
            build_plugin.build(output, check_only=True)


if __name__ == "__main__":
    unittest.main()
