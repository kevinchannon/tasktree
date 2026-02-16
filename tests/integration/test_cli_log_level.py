"""Integration tests for --log-level CLI flag."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from helpers.io import strip_ansi_codes


class TestLogLevelCLIFlag(unittest.TestCase):
    """
    Test that --log-level CLI flag correctly controls log output verbosity.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_log_level_flag_accepts_all_levels(self):
        """
        Test that --log-level accepts all six valid levels.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Hello world"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test each log level
                for level in ["fatal", "error", "warn", "info", "debug", "trace"]:
                    result = self.runner.invoke(
                        app, ["--log-level", level, "simple"], env=self.env
                    )
                    # Should not fail due to invalid log level
                    self.assertEqual(
                        result.exit_code,
                        0,
                        f"Log level '{level}' should be valid, but got exit code {result.exit_code}",
                    )

            finally:
                os.chdir(original_cwd)

    def test_log_level_flag_short_form(self):
        """
        Test that -L short form works.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Hello world"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test short form -L
                result = self.runner.invoke(
                    app, ["-L", "debug", "simple"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

            finally:
                os.chdir(original_cwd)

    def test_log_level_default_is_info(self):
        """
        Test that default log level is INFO (preserves current behavior).
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Hello world"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run without --log-level flag
                result = self.runner.invoke(app, ["simple"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                # Should see normal info-level messages
                self.assertIn("Task 'simple' completed successfully", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_log_level_with_list_command(self):
        """
        Test that --log-level works with --list command.
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

                # Test --log-level with --list
                result = self.runner.invoke(
                    app, ["--log-level", "debug", "--list"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)
                self.assertIn("task1", result.stdout)
                self.assertIn("task2", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_log_level_case_insensitive(self):
        """
        Test that log level parsing is case-insensitive.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Hello world"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test various case combinations
                for level in ["INFO", "Info", "iNfO", "DEBUG", "Debug"]:
                    result = self.runner.invoke(
                        app, ["--log-level", level, "simple"], env=self.env
                    )
                    self.assertEqual(
                        result.exit_code,
                        0,
                        f"Log level '{level}' (case variant) should work",
                    )

            finally:
                os.chdir(original_cwd)

    def test_log_level_invalid_value_produces_error(self):
        """
        Test that invalid log level values produce clear error messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  simple:
    desc: A simple task
    cmd: echo "Hello world"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test invalid log level values
                invalid_levels = ["verbose", "warning", "critical", "123"]

                for invalid in invalid_levels:
                    result = self.runner.invoke(
                        app, ["--log-level", invalid, "simple"], env=self.env
                    )
                    # Should fail with exit code 2 (click.BadParameter)
                    self.assertEqual(
                        result.exit_code,
                        2,
                        f"Invalid log level '{invalid}' should produce exit code 2, got {result.exit_code}",
                    )
                    # Error message should indicate invalid choice
                    output = strip_ansi_codes(result.output)
                    self.assertIn(
                        "is not one of",
                        output.lower(),
                        f"Error message for '{invalid}' should indicate it's not a valid choice",
                    )

            finally:
                os.chdir(original_cwd)
