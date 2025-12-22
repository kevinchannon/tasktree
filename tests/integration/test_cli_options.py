"""Integration tests for CLI options vs user task names."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class TestCLIOptionsNoClash(unittest.TestCase):
    """Test that CLI options (--show, --tree, etc.) don't clash with user task names."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_user_tasks_with_builtin_names(self):
        """Test that user can create tasks named 'show', 'tree', 'init', etc.

        This verifies that built-in options (--show, --tree, --init) don't prevent
        users from creating tasks with those names.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml with tasks named after built-in options
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
show:
  desc: User task named 'show'
  cmd: echo "Running user's show task"

tree:
  desc: User task named 'tree'
  cmd: echo "Running user's tree task"

init:
  desc: User task named 'init'
  cmd: echo "Running user's init task"

list:
  desc: User task named 'list'
  cmd: echo "Running user's list task"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test 1: User tasks can be executed
                result = self.runner.invoke(app, ["show"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'show' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["tree"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'tree' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["init"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'init' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["list"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'list' completed successfully", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_builtin_options_still_work(self):
        """Test that built-in options still work when user has tasks with same names."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml with tasks named after built-in options
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
show:
  desc: User task named 'show'
  cmd: echo "Running user's show task"

build:
  desc: Build task
  outputs: [output.txt]
  cmd: echo "building" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test that --show (built-in option) still works
                result = self.runner.invoke(app, ["--show", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build:", result.stdout)
                self.assertIn("desc: Build task", result.stdout)
                # Should NOT execute the user's "show" task
                self.assertNotIn("Running user's show task", result.stdout)

                # Test that --list (built-in option) still works
                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Available Tasks", result.stdout)
                self.assertIn("show", result.stdout)
                self.assertIn("build", result.stdout)

                # Test that --tree (built-in option) still works
                result = self.runner.invoke(app, ["--tree", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build", result.stdout)
                # Should NOT execute the user's "show" task
                self.assertNotIn("Running user's show task", result.stdout)
            finally:
                os.chdir(original_cwd)

            # Test that --init creates a new file (in a subdir to not conflict)
            init_dir = project_root / "subdir"
            init_dir.mkdir()
            original_cwd = os.getcwd()
            try:
                os.chdir(init_dir)
                result = self.runner.invoke(app, ["--init"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((init_dir / "tasktree.yaml").exists())
                self.assertIn("Created", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_double_dash_required_for_options(self):
        """Test that single-word options don't work - must use double-dash."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  cmd: echo "building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Single word "show" should be treated as a task name (and fail)
                result = self.runner.invoke(app, ["show", "build"], env=self.env)
                # This should fail because "show" task doesn't exist
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("Task not found: show", result.stdout)

                # But --show should work
                result = self.runner.invoke(app, ["--show", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build:", result.stdout)
            finally:
                os.chdir(original_cwd)


    def test_help_option_works(self):
        """Test that --help and -h options work correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  cmd: echo "building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test --help
                result = self.runner.invoke(app, ["--help"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task Tree", result.stdout)
                self.assertIn("Usage:", result.stdout)
                # Typer formats it with a box, so just check for "Options"
                self.assertIn("Options", result.stdout)
                self.assertIn("--help", result.stdout)
                self.assertIn("--version", result.stdout)
                self.assertIn("--list", result.stdout)
                self.assertIn("--show", result.stdout)
                self.assertIn("--tree", result.stdout)
                self.assertIn("--dry-run", result.stdout)
                self.assertIn("--init", result.stdout)
                self.assertIn("--clean", result.stdout)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
