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

    def test_mirror_list_is_copied(self):
        self.assertIn("mirrors = list(configured_mirrors)", SOURCE)

    def test_malformed_rows_are_skipped(self):
        self.assertIn("if len(columns) <= 9:", SOURCE)

    def test_filter_values_are_url_encoded(self):
        self.assertIn("url += f'&{urlencode({option.url_param: item})}'", SOURCE)

    def test_missing_mirror_fails_clearly(self):
        self.assertIn("No Anna's Archive mirror is configured.", SOURCE)


if __name__ == "__main__":
    unittest.main()
