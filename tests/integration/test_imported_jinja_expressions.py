"""
Integration tests for var.* references inside Jinja expressions in imported
files (schema pipeline slice 9).

The merge namespaces an imported file's variable references so they resolve
against its own variables. What these tests pin is the *scope* half of that:
an imported reference inside a filter or conditional no longer silently
resolves to a same-named variable in the importing file.

Actually rendering such a reference is a separate, larger gap: var.* is
substituted textually at parse time and the task render context carries no
var namespace, so a var.* reference inside any Jinja expression fails --
in imported and plain recipes alike, on this branch and on v1.3.2. Slice 7
owns that, because making it work without the hash change would stop
variable edits from triggering re-runs. Until then these tasks fail, and
they must fail *loudly*, naming the namespaced variable.

Self-contained (only v1.3.2-era symbols) so the file can be copied into the
reference worktree for the gate run.
"""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class ImportedExpressionTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)
        self.addCleanup(lambda: os.chdir(self._original_cwd))

    def write(self, name: str, text: str) -> Path:
        path = self.project_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_task(self, task: str):
        result = self.runner.invoke(app, [task], env=self.env)
        return result, strip_ansi_codes(result.stdout)


class TestImportedExpressionsDoNotLeakScope(ImportedExpressionTestCase):
    """
    The dangerous case: the importing file defines a variable of the same
    name. An un-namespaced reference would quietly use the importer's value
    and produce a wrong result with no error at all.
    """

    def test_filtered_reference_does_not_use_the_importers_variable(self):
        self.write(
            "tt.yaml",
            "variables:\n"
            "  greeting: root-value\n"
            "imports:\n  - file: build.yaml\n    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  greeting: imported-value\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: echo {{ var.greeting | upper }}\n",
        )
        result, output = self.run_task("build.hi")
        self.assertNotIn("ROOT-VALUE", output)
        self.assertNotEqual(result.exit_code, 0, output)

    def test_reference_is_resolved_under_its_namespace_not_bare(self):
        """
        The lookup that fails must be the namespaced one. Before the fix the
        reference stayed bare, so the failure named 'greeting' -- proof it
        was being looked up in the importer's scope.
        """
        self.write(
            "tt.yaml",
            "imports:\n  - file: build.yaml\n    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  greeting: imported\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: echo {{ var.greeting | upper }}\n",
        )
        result, output = self.run_task("build.hi")
        self.assertNotEqual(result.exit_code, 0, output)
        self.assertNotIn("attribute 'greeting'", output)
        self.assertIn("attribute 'build'", output)

    def test_whole_block_reference_still_works(self):
        """Parity: the form that has always worked is unaffected."""
        self.write(
            "tt.yaml",
            "variables:\n"
            "  greeting: root-value\n"
            "imports:\n  - file: build.yaml\n    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  greeting: imported-value\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: echo {{ var.greeting }}\n",
        )
        result, output = self.run_task("build.hi")
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("imported-value", output)


class TestPlainRecipesShareTheLimitation(ImportedExpressionTestCase):
    """
    Imports are not what breaks expression references -- nothing supports
    them yet. Pinning that here keeps the slice 9 fix from being blamed for
    it, and gives slice 7 a test that flips when the capability lands.
    """

    def test_expression_reference_fails_without_any_import(self):
        self.write(
            "tt.yaml",
            "variables:\n"
            "  greeting: hello\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: echo {{ var.greeting | upper }}\n",
        )
        result, output = self.run_task("hi")
        self.assertNotEqual(result.exit_code, 0, output)

    def test_whole_block_reference_works_without_any_import(self):
        self.write(
            "tt.yaml",
            "variables:\n"
            "  greeting: hello\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: echo {{ var.greeting }}\n",
        )
        result, output = self.run_task("hi")
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("hello", output)


if __name__ == "__main__":
    unittest.main()
