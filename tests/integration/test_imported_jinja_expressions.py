"""
Integration tests for var.* references inside Jinja expressions in imported
files (schema pipeline slice 9).

The merge namespaces an imported file's variable references so they resolve
against its own variables. What these tests pin is the *scope* half of that:
an imported reference inside a filter or conditional no longer silently
resolves to a same-named variable in the importing file.

Rendering such a reference was a separate, larger gap -- var.* was
substituted textually at parse time and the task render context carried no
var namespace, so a reference inside any Jinja expression failed, in
imported and plain recipes alike. Slice 7 closed it, once the hash counted
referenced values so that variable edits still trigger re-runs.

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


class TestImportedExpressionsResolveInTheirOwnScope(ImportedExpressionTestCase):
    """
    The dangerous case: the importing file defines a variable of the same
    name. An un-namespaced reference would quietly use the importer's value
    and produce a wrong result with no error at all.
    """

    def test_filtered_reference_uses_the_imported_variable(self):
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
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("IMPORTED-VALUE", output)
        self.assertNotIn("ROOT-VALUE", output)

    def test_conditional_reference_uses_the_imported_variables(self):
        """Every reference in the expression resolves in the imported scope."""
        self.write(
            "tt.yaml",
            "imports:\n  - file: build.yaml\n    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  debug_flag: '-g'\n"
            "  release_flag: '-O2'\n"
            "  is_debug: 'true'\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: \"echo {{ var.debug_flag if var.is_debug == 'true' "
            'else var.release_flag }}"\n',
        )
        result, output = self.run_task("build.hi")
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("-g", output)

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


class TestPlainRecipesToo(ImportedExpressionTestCase):
    """
    Expression references work the same without any import in sight.
    """

    def test_expression_reference_renders_without_any_import(self):
        self.write(
            "tt.yaml",
            "variables:\n"
            "  greeting: hello\n"
            "tasks:\n"
            "  hi:\n"
            "    cmd: echo {{ var.greeting | upper }}\n",
        )
        result, output = self.run_task("hi")
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("HELLO", output)

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
