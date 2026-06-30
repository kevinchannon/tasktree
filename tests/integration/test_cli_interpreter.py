"""Integration tests for the --interpreter CLI flag (issue #201, step 8)."""

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


class TestCliInterpreter(unittest.TestCase):
    """The --interpreter flag overrides the interpreter for all tasks."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    @unittest.skipIf(sys.platform == "win32", "python3 command not available on Windows")
    def test_interpreter_flag_selects_python(self):
        """`tt greet -i python3` runs a Python cmd that bash could not."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                copy_fixture_files("cli_interpreter", project_root)

                result = self.runner.invoke(
                    app, ["--interpreter", "python3", "greet"], env=self.env
                )
                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )
                out = project_root / "out.txt"
                self.assertTrue(out.exists(), "Output file was not created")
                self.assertIn("from python", out.read_text())
            finally:
                os.chdir(original_cwd)

    def test_unknown_interpreter_flag_errors(self):
        """An unknown --interpreter value exits non-zero with a helpful message."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                copy_fixture_files("cli_interpreter", project_root)

                result = self.runner.invoke(
                    app, ["--interpreter", "nonsuch", "greet"], env=self.env
                )
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("nonsuch", result.stdout)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
