"""Integration tests for --clean-state option and its aliases."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestCleanState(unittest.TestCase):
    """Test that --clean-state and its aliases work correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_clean_state_removes_state_file(self):
        """Test that --clean-state removes the .tasktree-state file."""
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

                # Run --clean-state
                result = self.runner.invoke(app, ["--clean-state"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Removed", strip_ansi_codes(result.stdout))

                # Verify state file was removed
                self.assertFalse(state_file.exists())
            finally:
                os.chdir(original_cwd)

    def test_clean_alias_works(self):
        """Test that --clean works as an alias for --clean-state."""
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

                # Run --clean (short alias)
                result = self.runner.invoke(app, ["--clean"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Removed", strip_ansi_codes(result.stdout))

                # Verify state file was removed
                self.assertFalse(state_file.exists())
            finally:
                os.chdir(original_cwd)

    def test_reset_alias_works(self):
        """Test that --reset works as an alias for --clean-state."""
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

                # Run --reset
                result = self.runner.invoke(app, ["--reset"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Removed", strip_ansi_codes(result.stdout))

                # Verify state file was removed
                self.assertFalse(state_file.exists())
            finally:
                os.chdir(original_cwd)

    def test_clean_state_when_no_state_file(self):
        """Test that --clean-state handles missing state file gracefully."""
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

            # Run --clean-state
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["--clean-state"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("No state file found", strip_ansi_codes(result.stdout))
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
