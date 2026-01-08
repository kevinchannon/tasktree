"""Integration tests for private tasks feature."""

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


class TestPrivateTasksExecution(unittest.TestCase):
    """Test execution of private tasks."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_private_task_hidden_from_list(self):
        """Test that private tasks are hidden from --list output."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  public-task:
    desc: This is public
    cmd: echo public

  private-task:
    private: true
    desc: This is private
    cmd: echo private
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)

                # Public task should appear
                self.assertIn("public-task", output)

                # Private task should NOT appear
                self.assertNotIn("private-task", output)
            finally:
                os.chdir(original_cwd)

    def test_private_task_can_be_executed(self):
        """Test that private tasks can still be executed directly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  private-task:
    private: true
    cmd: echo "private executed"
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["private-task"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'private-task' completed successfully", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_private_task_as_dependency(self):
        """Test that private tasks work as dependencies."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_file = project_root / "tasktree.yaml"
            output_file = project_root / "output.txt"
            recipe_file.write_text(f"""
tasks:
  helper:
    private: true
    cmd: echo "helper" > {output_file}

  main:
    deps: [helper]
    cmd: echo "main" >> {output_file}
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Execute main task
                result = self.runner.invoke(app, ["main"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Both tasks should have executed
                content = output_file.read_text()
                self.assertIn("helper", content)
                self.assertIn("main", content)
            finally:
                os.chdir(original_cwd)

    def test_private_task_with_arguments(self):
        """Test that private tasks with arguments can be executed."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  private-with-args:
    private: true
    args:
      - mode
    cmd: echo "mode is {{ arg.mode }}"
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["private-with-args", "debug"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'private-with-args' completed successfully", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_mixed_private_and_public_tasks_in_list(self):
        """Test list output with mix of private and public tasks."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  task1:
    cmd: echo 1

  task2:
    private: true
    cmd: echo 2

  task3:
    cmd: echo 3

  task4:
    private: true
    cmd: echo 4

  task5:
    cmd: echo 5
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)

                # Public tasks should appear
                self.assertIn("task1", output)
                self.assertIn("task3", output)
                self.assertIn("task5", output)

                # Private tasks should NOT appear
                self.assertNotIn("task2", output)
                self.assertNotIn("task4", output)
            finally:
                os.chdir(original_cwd)

    def test_private_task_in_namespace(self):
        """Test private tasks in imported namespaces."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create base tasks file
            base_file = project_root / "base.tasks"
            base_file.write_text("""
tasks:
  helper:
    private: true
    cmd: echo helper

  main:
    cmd: echo main
""")

            # Create main recipe that imports base
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
imports:
  - file: base.tasks
    as: base

tasks:
  root:
    cmd: echo root
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Check list output
                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)

                # Public tasks should appear
                self.assertIn("base.main", output)
                self.assertIn("root", output)

                # Private task should NOT appear
                self.assertNotIn("base.helper", output)

                # But private task can still be executed
                result = self.runner.invoke(app, ["base.helper"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'base.helper' completed successfully", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_all_tasks_private_shows_empty_list(self):
        """Test that list shows empty when all tasks are private."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  private1:
    private: true
    cmd: echo 1

  private2:
    private: true
    cmd: echo 2
""")
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)

                # Should not contain task names
                self.assertNotIn("private1", output)
                self.assertNotIn("private2", output)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
