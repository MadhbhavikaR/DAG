import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src" / "annas_archive.py").read_text(encoding="utf-8")


class SourceRegressionTests(unittest.TestCase):
    def test_extension_filter_uses_negative_condition(self):
        self.assertIn("if not path.endswith(_format):", SOURCE)

    def test_query_strings_are_removed_before_extension_check(self):
        self.assertIn('path = url.split("?", 1)[0].lower()', SOURCE)

    def test_libgen_and_zlib_use_urljoin(self):
        self.assertIn("return urljoin(base_url, target)", SOURCE)
        self.assertGreaterEqual(SOURCE.count("return urljoin(base_url, target)"), 2)


    def test_malformed_rows_are_skipped(self):
        self.assertIn("if len(columns) <= 9:", SOURCE)

    def test_filter_values_are_url_encoded(self):
        self.assertIn("url += f'&{urlencode({option.url_param: item})}'", SOURCE)

    def test_missing_mirror_fails_clearly(self):
        self.assertIn("No Anna's Archive mirror is configured.", SOURCE)


if __name__ == "__main__":
    unittest.main()


class MirrorConfigurationTests(unittest.TestCase):
    def test_new_default_mirror_is_first_and_only_default(self):
        constants = (ROOT / "src" / "constants.py").read_text(encoding="utf-8")
        self.assertIn("DEFAULT_MIRRORS = ['https://annas-archive.gd']", constants)

    def test_mirror_editor_has_add_edit_delete_actions(self):
        config = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
        for action in ("add_mirror", "edit_mirror", "delete_mirror"):
            self.assertIn("def " + action + "(self):", config)
        for label in ("Add", "Edit", "Delete"):
            self.assertIn("QPushButton(_('"+label+"')", config)

    def test_mirror_values_are_trimmed_and_deduplicated(self):
        config = (ROOT / "src" / "config.py").read_text(encoding="utf-8")
        self.assertIn("str(self.item(i).text()).strip().rstrip('/')", config)
        self.assertIn("if mirror and mirror not in mirrors:", config)
