"""Integration tests for the task-level 'interpreter' field (issue #201)."""

import os
import shlex
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


class TestTaskInterpreter(unittest.TestCase):
    """A task's 'interpreter' field selects the interpreter without a runner."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    @unittest.skipIf(sys.platform == "win32", "python3 command not available on Windows")
    def test_task_interpreter_runs_command_with_python(self):
        """A task with interpreter: python3 runs its cmd as a Python script."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("task_interpreter", project_root)

                result = self.runner.invoke(app, ["test-python"], env=self.env)

                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("Hello from task interpreter", output_file.read_text())
            finally:
                os.chdir(original_cwd)

    def test_runner_interpreter_string_shorthand_runs_command(self):
        """A runner whose `interpreter` is a bare string runs the task with it.

        Uses the running interpreter (sys.executable) as the bare-string
        interpreter so the test exercises the shorthand on every platform
        rather than skipping where a 'python3' command happens not to exist.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                # shlex.quote so a path with spaces/backslashes (e.g. on Windows)
                # round-trips through the interpreter's shlex.split() as one token;
                # yaml.safe_dump then escapes it so the parsed scalar is exactly
                # that quoted string (not consumed by YAML's own quoting).
                recipe = {
                    "runners": {"py": {"interpreter": shlex.quote(sys.executable)}},
                    "tasks": {
                        "test-python": {
                            "run_in": "py",
                            "cmd": (
                                'with open("output.txt", "w") as f:\n'
                                '    f.write("Hello from string interpreter\\n")\n'
                            ),
                        }
                    },
                }
                (project_root / "tasktree.yaml").write_text(yaml.safe_dump(recipe))

                result = self.runner.invoke(app, ["test-python"], env=self.env)

                self.assertEqual(
                    result.exit_code, 0, f"Command failed: {result.stdout}"
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("Hello from string interpreter", output_file.read_text())
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
