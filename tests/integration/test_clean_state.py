"""Integration tests for --clean option and its aliases."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from tests.fixture_utils import copy_fixture_files


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestCleanState(unittest.TestCase):
    """
    Test that --clean and its aliases work correctly.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_clean_removes_state_file(self):
        """
        Test that --clean removes the .tasktree-state file.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("clean_removes_state_file", project_root)

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
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("clean_when_no_state_file", project_root)

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
