"""Integration tests for log level filtering during task execution."""

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
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


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

                output = strip_ansi_codes(result.output)
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

                output = strip_ansi_codes(result.output)
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

                output = strip_ansi_codes(result.output)
                # Should see normal completion message
                self.assertIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_debug_level_shows_more_detail(self):
        """
        Test that DEBUG level shows additional diagnostic information.

        Note: This test verifies that debug level accepts the flag correctly.
        Actual debug output will be added in later commits when debug logging
        is integrated into the executor.
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

                # Run with DEBUG level - should succeed
                result = self.runner.invoke(
                    app, ["--log-level", "debug", "simple"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                # Should still see normal info messages
                output = strip_ansi_codes(result.output)
                self.assertIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_trace_level_shows_fine_grained_detail(self):
        """
        Test that TRACE level works correctly.

        Note: This test verifies that trace level accepts the flag correctly.
        Actual trace output will be added in later commits when trace logging
        is integrated into the executor.
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

                # Run with TRACE level - should succeed
                result = self.runner.invoke(
                    app, ["--log-level", "trace", "simple"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                # Should still see normal info messages
                output = strip_ansi_codes(result.output)
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

                output = strip_ansi_codes(result.output)
                # Should see INFO-level messages (completed successfully)
                self.assertIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)

    def test_log_level_affects_list_command(self):
        """
        Test that log level filtering works with --list command.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  task1:
    desc: First task
    cmd: echo "Task 1"
  task2:
    desc: Second task
    cmd: echo "Task 2"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test with FATAL level (should still show task list)
                result = self.runner.invoke(
                    app, ["--log-level", "fatal", "--list"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)
                # List output is informational, not diagnostic logging,
                # so it should still appear
                self.assertIn("task1", result.output)
                self.assertIn("task2", result.output)

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

                output = strip_ansi_codes(result.output)
                # Should see completion message
                self.assertIn("completed successfully", output.lower())

                # Run again with FATAL level - should suppress progress messages
                (project_root / "dep.txt").unlink()  # Force re-run
                result = self.runner.invoke(
                    app, ["--log-level", "fatal", "main"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.output)
                # Should NOT see completion messages at FATAL level
                self.assertNotIn("completed successfully", output.lower())

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
