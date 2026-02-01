"""Integration tests for task output control."""

import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from helpers.logging import logger_stub
from tasktree.cli import app
from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager


class TestTaskOutputOption(unittest.TestCase):
    """
    Test the --task-output/-O option for controlling task subprocess output.
    @athena: 734c86c82841
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 563ac9b21ae9
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_task_output_all_is_default(self):
        """
        Test that --task-output=all is the default and passes through output.
        @athena: 76e91efa2bd1
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
        @athena: 441adfee697b
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
        @athena: 65d072f2e598
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


class TestStdoutOnlyProcessRunnerIntegration(unittest.TestCase):
    """
    Integration tests for StdoutOnlyProcessRunner with Executor.
    @athena: TBD
    """

    def test_stdout_only_runner_with_executor(self):
        """
        Test that StdoutOnlyProcessRunner can be used with Executor for tasks
        that produce both stdout and stderr, and only stdout is shown.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a recipe with a task that outputs to both stdout and stderr
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: python3 -c "import sys; print('stdout output'); sys.stderr.write('stderr output\\n')"
""")

            # Parse the recipe
            recipe = parse_recipe(recipe_file)

            # Create state manager and executor
            state_manager = StateManager(project_root)
            state_manager.load()
            executor = Executor(
                recipe,
                state_manager,
                logger_stub,
                make_process_runner,
            )

            # Execute the task with OUT mode, capturing stdout and stderr
            original_cwd = os.getcwd()
            captured_stdout = io.StringIO()
            captured_stderr = io.StringIO()

            try:
                os.chdir(project_root)
                # Redirect sys.stdout and sys.stderr to capture output
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = captured_stdout
                sys.stderr = captured_stderr

                try:
                    executor.execute_task("test", TaskOutputTypes.OUT)
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                # Verify stdout was captured (streamed through)
                stdout_content = captured_stdout.getvalue()
                self.assertIn("stdout output", stdout_content)

                # Verify stderr was NOT captured (suppressed)
                stderr_content = captured_stderr.getvalue()
                self.assertNotIn("stderr output", stderr_content)

            finally:
                os.chdir(original_cwd)

    def test_stdout_only_runner_handles_task_failure(self):
        """
        Test that StdoutOnlyProcessRunner properly handles task failures.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a recipe with a failing task
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  fail:
    cmd: python3 -c "import sys; print('before failure'); sys.exit(1)"
""")

            # Parse the recipe
            recipe = parse_recipe(recipe_file)

            # Create state manager and executor
            state_manager = StateManager(project_root)
            state_manager.load()
            executor = Executor(
                recipe,
                state_manager,
                logger_stub,
                make_process_runner,
            )

            # Execute the task with OUT mode - should raise an exception
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                with self.assertRaises(subprocess.CalledProcessError):
                    executor.execute_task("fail", TaskOutputTypes.OUT)

            finally:
                os.chdir(original_cwd)

    def test_rapid_successive_task_execution(self):
        """
        Test that threads are properly cleaned up during rapid successive executions.
        @athena: TBD
        """
        import threading

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a recipe with a quick task
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  quick:
    cmd: python3 -c "print('quick task')"
""")

            # Parse the recipe
            recipe = parse_recipe(recipe_file)

            # Create state manager and executor
            state_manager = StateManager(project_root)
            state_manager.load()
            executor = Executor(
                recipe,
                state_manager,
                logger_stub,
                make_process_runner,
            )

            # Execute the task multiple times rapidly
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                initial_thread_count = threading.active_count()

                # Run task 10 times rapidly
                for _ in range(10):
                    executor.execute_task("quick", TaskOutputTypes.OUT, force=True)

                # Verify thread count hasn't grown (threads were cleaned up)
                final_thread_count = threading.active_count()
                self.assertEqual(
                    initial_thread_count,
                    final_thread_count,
                    "Thread count should not increase after multiple task executions",
                )

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
