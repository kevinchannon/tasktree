"""Integration tests for task output control."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class TestTaskOutputOption(unittest.TestCase):
    """
    Test the --task-output/-O option for controlling task subprocess output.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_task_output_all_is_default(self):
        """
        Test that --task-output=all is the default and passes through output.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello from task"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run without --task-output (should use default "all")
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'test' completed successfully", result.stdout)
                # Verify task output is actually displayed
                self.assertIn("Hello from task", result.stdout)

                # Run with explicit --task-output=all
                result = self.runner.invoke(
                    app, ["--task-output", "all", "test"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'test' completed successfully", result.stdout)
                # Verify task output is actually displayed
                self.assertIn("Hello from task", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_task_output_short_flag_works(self):
        """
        Test -O short flag works as alias for --task-output.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    cmd: echo "Building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with -O short flag
                result = self.runner.invoke(app, ["-O", "all", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'build' completed successfully", result.stdout)
                # Verify task output is actually displayed
                self.assertIn("Building", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_task_output_case_insensitive(self):
        """
        Test that --task-output accepts case-insensitive values.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Testing"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test various case variations
                for value in ["all", "ALL", "All", "aLl"]:
                    result = self.runner.invoke(
                        app, ["--task-output", value, "test"], env=self.env
                    )
                    self.assertEqual(
                        result.exit_code,
                        0,
                        f"Failed with --task-output={value}",
                    )
                    self.assertIn("Task 'test' completed successfully", result.stdout)
                    # Verify task output is actually displayed
                    self.assertIn("Testing", result.stdout)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
