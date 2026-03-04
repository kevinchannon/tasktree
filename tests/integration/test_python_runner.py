"""Integration tests for running tasks with a Python interpreter runner."""

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


class TestPythonRunner(unittest.TestCase):
    """
    Test that a runner configured with shell: python3 executes tasks correctly.

    This validates the shell-agnostic execution model: shell_cmd + [script_path]
    works for any interpreter, not just bash/sh.
    """

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    @unittest.skipUnless(sys.platform != "win32", "posix only: uses python3")
    def test_python_runner_executes_python_script(self):
        """
        Test that a task with run_in: python3 runner executes as a Python script.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("python_runner", project_root)

                result = self.runner.invoke(app, ["test-python"], env=self.env)

                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Command failed: {result.stdout}",
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("Hello from Python", output_file.read_text())
            finally:
                os.chdir(original_cwd)
