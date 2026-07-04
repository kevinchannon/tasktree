"""Unit tests for the raw-dict import merge (schema pipeline slice 4)."""

import tempfile
import unittest
from pathlib import Path

from tasktree.raw_merge import CircularImportError, merge_recipe


class RawMergeTestCase(unittest.TestCase):
    """Base: a temp directory to write recipe fixture files into."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class TestNoImports(RawMergeTestCase):
    def test_file_without_imports_round_trips(self):
        recipe = self.write(
            "tt.yaml",
            "tasks:\n"
            "  build:\n"
            "    cmd: make\n"
            "variables:\n"
            "  version: 1.2.3\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged,
            {
                "tasks": {"build": {"cmd": "make"}},
                "variables": {"version": "1.2.3"},
            },
        )

    def test_empty_file_merges_to_empty_dict(self):
        recipe = self.write("tt.yaml", "")
        self.assertEqual(merge_recipe(recipe), {})

    def test_comment_only_file_merges_to_empty_dict(self):
        recipe = self.write("tt.yaml", "# nothing here\n")
        self.assertEqual(merge_recipe(recipe), {})


class TestImportErrors(RawMergeTestCase):
    def test_missing_import_file_raises(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: nope.yaml\n"
            "    as: nope\n",
        )
        with self.assertRaises(FileNotFoundError) as cm:
            merge_recipe(recipe)
        self.assertIn("Import file not found", str(cm.exception))
        self.assertIn("nope.yaml", str(cm.exception))

    def test_self_import_raises_circular(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: tt.yaml\n"
            "    as: me\n",
        )
        with self.assertRaises(CircularImportError) as cm:
            merge_recipe(recipe)
        self.assertEqual(
            str(cm.exception), "Circular import detected: tt.yaml → tt.yaml"
        )

    def test_mutual_import_raises_circular_with_chain(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: other.yaml\n"
            "    as: other\n",
        )
        self.write(
            "other.yaml",
            "imports:\n"
            "  - file: tt.yaml\n"
            "    as: main\n",
        )
        with self.assertRaises(CircularImportError) as cm:
            merge_recipe(recipe)
        self.assertEqual(
            str(cm.exception),
            "Circular import detected: tt.yaml → other.yaml → tt.yaml",
        )

    def test_diamond_import_is_not_circular(self):
        # Two routes to the same file must not be mistaken for a cycle
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: left.yaml\n"
            "    as: left\n"
            "  - file: right.yaml\n"
            "    as: right\n",
        )
        self.write(
            "left.yaml",
            "imports:\n"
            "  - file: shared.yaml\n"
            "    as: shared\n",
        )
        self.write(
            "right.yaml",
            "imports:\n"
            "  - file: shared.yaml\n"
            "    as: shared\n",
        )
        self.write("shared.yaml", "tasks:\n  t:\n    cmd: echo\n")
        merge_recipe(recipe)  # Must not raise

    def test_imports_key_is_consumed(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: other.yaml\n"
            "    as: other\n"
            "tasks:\n"
            "  t:\n"
            "    cmd: echo\n",
        )
        self.write("other.yaml", "tasks:\n  o:\n    cmd: echo\n")
        merged = merge_recipe(recipe)
        self.assertNotIn("imports", merged)


if __name__ == "__main__":
    unittest.main()
