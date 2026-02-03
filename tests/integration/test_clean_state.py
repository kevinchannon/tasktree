"""Integration tests for --clean option and its aliases."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    @athena: 853120f3304f
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestCleanState(unittest.TestCase):
    """
    Test that --clean and its aliases work correctly.
    @athena: 4391efb2c247
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 563ac9b21ae9
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_clean_removes_state_file(self):
        """
        Test that --clean removes the .tasktree-state file.
        @athena: 545ac4a8ddca
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    desc: Build task
    outputs: [output.txt]
    cmd: echo "building" > output.txt
""")

            # Run a task to create state file
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify state file was created
                state_file = project_root / ".tasktree-state"
                self.assertTrue(state_file.exists())

                result = self.runner.invoke(app, ["--clean"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Removed", strip_ansi_codes(result.stdout))

                # Verify state file was removed
                self.assertFalse(state_file.exists())
            finally:
                os.chdir(original_cwd)

    def test_clean_when_no_state_file(self):
        """
        Test that --clean handles missing state file gracefully.
        @athena: 5b5f8d270dc9
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    desc: Build task
    cmd: echo "building"
""")

            # State file doesn't exist yet
            state_file = project_root / ".tasktree-state"
            self.assertFalse(state_file.exists())

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["--clean"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("No state file found", strip_ansi_codes(result.stdout))
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
