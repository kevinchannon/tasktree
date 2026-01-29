"""Integration tests for log level filtering during task execution."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from helpers.io import strip_ansi_codes


class TestCLILogging(unittest.TestCase):
    """
    Test that --log-level correctly filters messages during task execution.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_fatal_level_suppresses_all_but_fatal(self):
        """
        Test that FATAL level only shows fatal errors, not normal execution messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Task running"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with FATAL level
                result = self.runner.invoke(
                    app, ["--log-level", "fatal", "simple"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)
                # Should NOT see normal execution messages
                self.assertNotIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_error_level_shows_errors(self):
        """
        Test that ERROR level shows task failures.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a failing task
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  failing:
    cmd: exit 1
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with ERROR level
                result = self.runner.invoke(
                    app, ["--log-level", "error", "failing"], env=self.env
                )
                self.assertNotEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)
                # Should see error messages
                self.assertIn("failed", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_info_level_shows_normal_execution(self):
        """
        Test that INFO level (default) shows normal execution progress.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Task running"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with INFO level
                result = self.runner.invoke(
                    app, ["--log-level", "info", "simple"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)
                # Should see normal completion message
                self.assertIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_higher_verbosity_includes_lower_levels(self):
        """
        Test that higher verbosity levels include messages from lower levels.

        For example, DEBUG should include INFO, WARN, ERROR, and FATAL messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    cmd: echo "Task running"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with DEBUG level
                result = self.runner.invoke(
                    app, ["--log-level", "debug", "simple"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)
                # Should see INFO-level messages (completed successfully)
                self.assertIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_log_level_with_dependencies(self):
        """
        Test that log level filtering works correctly with task dependencies.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with dependencies
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  dep:
    outputs: [dep.txt]
    cmd: echo "dependency" > dep.txt

  main:
    deps: [dep]
    cmd: echo "main task"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with INFO level - should see both tasks
                result = self.runner.invoke(
                    app, ["--log-level", "info", "main"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)
                # Should see completion message
                self.assertIn("completed successfully", output.lower())

                # Run again with FATAL level - should suppress progress messages
                (project_root / "dep.txt").unlink()  # Force re-run
                result = self.runner.invoke(
                    app, ["--log-level", "fatal", "main"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)
                # Should NOT see completion messages at FATAL level
                self.assertNotIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)
