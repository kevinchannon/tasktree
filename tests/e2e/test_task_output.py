"""E2E tests for task output control."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


class TestTaskOutputControl(unittest.TestCase):
    """
    Test --task-output option for controlling task subprocess output.
    These are E2E tests because CliRunner interferes with subprocess stdout/stderr handling.
    """

    def test_task_output_none_suppresses_all_output(self):
        """
        Test that --task-output=none suppresses all task subprocess output.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  noisy:
    cmd: |
      echo "stdout message"
      echo "stderr message" >&2
""")

            # Run with --task-output=none
            result = run_tasktree_cli(["--task-output", "none", "noisy"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Task completion message should still appear (that's not task output)
            self.assertIn("Task 'noisy' completed successfully", result.stdout)

            # Task subprocess output should NOT appear
            self.assertNotIn("stdout message", result.stdout)
            self.assertNotIn("stderr message", result.stdout)
            self.assertNotIn("stderr message", result.stderr)

    def test_task_output_none_short_flag(self):
        """
        Test -O none works correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    cmd: echo "Building application"
""")

            # Run with -O none
            result = run_tasktree_cli(["-O", "none", "build"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Task completion message should appear
            self.assertIn("Task 'build' completed successfully", result.stdout)

            # Task subprocess output should NOT appear
            self.assertNotIn("Building application", result.stdout)

    def test_task_output_none_case_insensitive(self):
        """
        Test that --task-output=none accepts case-insensitive values.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Test output"
""")

            # Test various case variations
            for value in ["none", "NONE", "None", "nOnE"]:
                result = run_tasktree_cli(
                    ["--task-output", value, "test"], cwd=project_root
                )

                # Assert success
                self.assertEqual(
                    result.returncode,
                    0,
                    f"Failed with --task-output={value}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
                )

                # Task completion message should appear
                self.assertIn("Task 'test' completed successfully", result.stdout)

                # Task subprocess output should NOT appear
                self.assertNotIn("Test output", result.stdout)


if __name__ == "__main__":
    unittest.main()
