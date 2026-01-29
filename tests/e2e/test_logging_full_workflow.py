"""E2E tests for logging across full workflow."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


class TestLoggingFullWorkflow(unittest.TestCase):
    """
    Test logging behavior across complete task execution workflows.
    """

    def test_fatal_level_suppresses_progress_messages(self):
        """
        Test that FATAL level suppresses all progress messages but task still executes.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with multiple tasks
            (project_root / "tasktree.yaml").write_text("""
tasks:
  build:
    outputs: [build.txt]
    cmd: echo "Building..." > build.txt

  test:
    deps: [build]
    outputs: [test.txt]
    cmd: echo "Testing..." > test.txt

  deploy:
    deps: [test]
    outputs: [deploy.txt]
    cmd: echo "Deploying..." > deploy.txt
""")

            # Run with FATAL level
            result = run_tasktree_cli(
                ["--log-level", "fatal", "deploy"], cwd=project_root
            )

            # Should succeed
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify all outputs were created (tasks executed)
            self.assertTrue((project_root / "build.txt").exists())
            self.assertTrue((project_root / "test.txt").exists())
            self.assertTrue((project_root / "deploy.txt").exists())

            # Verify no progress messages in stdout
            self.assertNotIn("completed successfully", result.stdout.lower())
            self.assertNotIn("task 'deploy'", result.stdout.lower())

    def test_info_level_shows_normal_progress(self):
        """
        Test that INFO level shows normal execution progress messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with multiple tasks
            (project_root / "tasktree.yaml").write_text("""
tasks:
  build:
    outputs: [build.txt]
    cmd: echo "Building..." > build.txt

  test:
    deps: [build]
    outputs: [test.txt]
    cmd: echo "Testing..." > test.txt
""")

            # Run with INFO level (default)
            result = run_tasktree_cli(["--log-level", "info", "test"], cwd=project_root)

            # Should succeed
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify outputs created
            self.assertTrue((project_root / "build.txt").exists())
            self.assertTrue((project_root / "test.txt").exists())

            # Verify progress messages are shown
            self.assertIn("completed successfully", result.stdout.lower())

    def test_error_level_shows_failures(self):
        """
        Test that ERROR level shows task failures with error messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with failing task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  failing:
    cmd: exit 42
""")

            # Run with ERROR level
            result = run_tasktree_cli(
                ["--log-level", "error", "failing"], cwd=project_root
            )

            # Should fail
            self.assertNotEqual(result.returncode, 0)

            # Should show error message
            self.assertIn("failed", result.stdout.lower())

    def test_debug_level_includes_info_messages(self):
        """
        Test that DEBUG level includes INFO-level messages (higher verbosity).

        Note: Actual debug-specific output will be added in later commits.
        This test verifies that debug level still shows info messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create simple recipe
            (project_root / "tasktree.yaml").write_text("""
tasks:
  build:
    outputs: [build.txt]
    cmd: echo "Building..." > build.txt
""")

            # Run with DEBUG level
            result = run_tasktree_cli(
                ["--log-level", "debug", "build"], cwd=project_root
            )

            # Should succeed
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Should show INFO-level completion message
            self.assertIn("completed successfully", result.stdout.lower())

    def test_trace_level_includes_all_lower_levels(self):
        """
        Test that TRACE level includes all lower-level messages.

        Note: Actual trace-specific output will be added in later commits.
        This test verifies that trace level still shows info messages.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create simple recipe
            (project_root / "tasktree.yaml").write_text("""
tasks:
  build:
    outputs: [build.txt]
    cmd: echo "Building..." > build.txt
""")

            # Run with TRACE level
            result = run_tasktree_cli(
                ["--log-level", "trace", "build"], cwd=project_root
            )

            # Should succeed
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Should show INFO-level completion message
            self.assertIn("completed successfully", result.stdout.lower())

    def test_log_level_with_parameterized_tasks(self):
        """
        Test that log level filtering works with parameterized tasks.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  deploy:
    args:
      - environment: { type: str, default: dev }
    outputs: [deploy.log]
    cmd: echo "Deploying to {{ arg.environment }}" > deploy.log
""")

            # Run with FATAL level - should suppress progress but still execute
            result = run_tasktree_cli(
                ["--log-level", "fatal", "deploy", "environment=prod"],
                cwd=project_root,
            )

            # Should succeed
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify task executed with correct parameter
            output_file = project_root / "deploy.log"
            self.assertTrue(output_file.exists())
            self.assertIn("Deploying to prod", output_file.read_text())

            # Should not see progress messages
            self.assertNotIn("completed successfully", result.stdout.lower())

    def test_log_level_with_incremental_execution(self):
        """
        Test that log level filtering works correctly with incremental execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with outputs
            (project_root / "tasktree.yaml").write_text("""
tasks:
  build:
    outputs: [build.txt]
    cmd: echo "Building..." > build.txt
""")

            # First run with INFO level
            result = run_tasktree_cli(
                ["--log-level", "info", "build"], cwd=project_root
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("completed successfully", result.stdout.lower())

            # Second run (should be up-to-date) with FATAL level
            result = run_tasktree_cli(
                ["--log-level", "fatal", "build"], cwd=project_root
            )
            self.assertEqual(result.returncode, 0)
            # Should not see any messages at FATAL level
            self.assertNotIn("completed successfully", result.stdout.lower())
            self.assertNotIn("up-to-date", result.stdout.lower())

    def test_log_level_with_force_flag(self):
        """
        Test that log level filtering works with --force flag.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
tasks:
  build:
    outputs: [build.txt]
    cmd: echo "Building..." > build.txt
""")

            # First run to create output
            result = run_tasktree_cli(["build"], cwd=project_root)
            self.assertEqual(result.returncode, 0)

            # Force re-run with FATAL level
            result = run_tasktree_cli(
                ["--log-level", "fatal", "--force", "build"], cwd=project_root
            )

            # Should succeed
            self.assertEqual(result.returncode, 0)

            # Should not see progress messages
            self.assertNotIn("completed successfully", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
