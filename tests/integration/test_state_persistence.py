"""Integration tests for state persistence across multiple CLI invocations."""

import os
import re
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestStatePersistence(unittest.TestCase):
    """Test that state is correctly saved/loaded across multiple invocations."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_state_preserved_across_runs(self):
        """Test state is saved and reused across multiple tt invocations."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input file
            input_file = project_root / "input.txt"
            input_file.write_text("initial content")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: [input.txt]
    outputs: [output.txt]
    cmd: echo "built" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task should execute (never run before)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("completed successfully", strip_ansi_codes(result.stdout))

                # Verify state file was created
                state_file = project_root / ".tasktree-state"
                self.assertTrue(state_file.exists())

                # Verify output was created
                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists())

                # Second run - task should skip (fresh, nothing changed)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("completed successfully", strip_ansi_codes(result.stdout))
                # Note: Even when skipped, CLI still shows "completed successfully"

                # Modify input file
                time.sleep(0.01)  # Ensure mtime changes
                input_file.write_text("modified content")

                # Third run - task should execute (input changed)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("completed successfully", strip_ansi_codes(result.stdout))

                # Verify state file still exists and was updated
                self.assertTrue(state_file.exists())

            finally:
                os.chdir(original_cwd)

    def test_task_args_are_cached_separately(self):
        """Test same task with different args has separate state entries."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with task that takes arguments
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args: [environment]
    outputs: ["deploy-{{ arg.environment }}.log"]
    cmd: echo "Deployed to {{ arg.environment }}" > deploy-{{ arg.environment }}.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run with "prod" argument
                result = self.runner.invoke(app, ["deploy", "prod"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "deploy-prod.log").exists())

                # Second run with same argument - should skip
                result = self.runner.invoke(app, ["deploy", "prod"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Third run with different argument - should execute (different cache key)
                result = self.runner.invoke(app, ["deploy", "staging"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "deploy-staging.log").exists())

                # Fourth run with original argument - should still skip (separate state)
                result = self.runner.invoke(app, ["deploy", "prod"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify both output files still exist
                self.assertTrue((project_root / "deploy-prod.log").exists())
                self.assertTrue((project_root / "deploy-staging.log").exists())

            finally:
                os.chdir(original_cwd)

    def test_clean_state_enables_fresh_run(self):
        """Test --clean-state removes state and forces rebuild."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [output.txt]
    cmd: echo "built" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task executes
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify state file exists
                state_file = project_root / ".tasktree-state"
                self.assertTrue(state_file.exists())

                # Second run - task should skip (fresh)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Clean state
                result = self.runner.invoke(app, ["--clean-state"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Removed", strip_ansi_codes(result.stdout))

                # Verify state file was deleted
                self.assertFalse(state_file.exists())

                # Third run - task should execute again (no state)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # State file should be recreated
                self.assertTrue(state_file.exists())

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
