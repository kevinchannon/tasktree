"""E2E tests for task output control via --task-output flag."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


class TestTaskOutputControl(unittest.TestCase):
    """
    Test --task-output flag functionality end-to-end.
    @athena: TBD
    """

    def test_task_output_all_shows_both_stdout_and_stderr(self):
        """
        Test that --task-output=all shows both stdout and stderr.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with task that outputs to both stdout and stderr
            (project_root / "tasktree.yaml").write_text("""
tasks:
  mixed-output:
    outputs: [done.txt]
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      echo "done" > done.txt
""")

            # Execute with --task-output=all
            result = run_tasktree_cli(
                ["--task-output=all", "mixed-output"], cwd=project_root
            )

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify both stdout and stderr appear in output
            self.assertIn("This is stdout", result.stdout)
            self.assertIn("This is stderr", result.stderr)

            # Verify output file was created
            output_file = project_root / "done.txt"
            self.assertTrue(output_file.exists(), "Output file not created")

    def test_task_output_out_shows_only_stdout(self):
        """
        Test that --task-output=out shows only stdout, suppresses stderr.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with task that outputs to both stdout and stderr
            (project_root / "tasktree.yaml").write_text("""
tasks:
  mixed-output:
    outputs: [done.txt]
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      echo "done" > done.txt
""")

            # Execute with --task-output=out
            result = run_tasktree_cli(
                ["--task-output=out", "mixed-output"], cwd=project_root
            )

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify stdout appears in output
            self.assertIn("This is stdout", result.stdout)

            # Verify stderr does NOT appear in output
            # (Note: stderr should be empty since it was suppressed)
            self.assertNotIn("This is stderr", result.stdout)
            self.assertNotIn("This is stderr", result.stderr)

            # Verify output file was created
            output_file = project_root / "done.txt"
            self.assertTrue(output_file.exists(), "Output file not created")

    def test_task_output_out_case_insensitive(self):
        """
        Test that --task-output accepts OUT in various cases (OUT, Out, out).
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with simple task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  simple:
    outputs: [done.txt]
    cmd: |
      echo "stdout message"
      echo "done" > done.txt
""")

            # Test uppercase
            result = run_tasktree_cli(["--task-output=OUT", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Uppercase OUT should be accepted")

            # Test mixed case
            result = run_tasktree_cli(["--task-output=Out", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Mixed case Out should be accepted")

    def test_task_output_out_with_short_flag(self):
        """
        Test that -O out works as short form of --task-output=out.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with task that outputs to both streams
            (project_root / "tasktree.yaml").write_text("""
tasks:
  mixed-output:
    outputs: [done.txt]
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      echo "done" > done.txt
""")

            # Execute with -O out
            result = run_tasktree_cli(["-O", "out", "mixed-output"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify stdout appears, stderr does not
            self.assertIn("This is stdout", result.stdout)
            self.assertNotIn("This is stderr", result.stdout)
            self.assertNotIn("This is stderr", result.stderr)

    def test_task_output_none_suppresses_all_output(self):
        """
        Test that --task-output=none suppresses both stdout and stderr.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with task that outputs to both stdout and stderr
            (project_root / "tasktree.yaml").write_text("""
tasks:
  mixed-output:
    outputs: [done.txt]
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      echo "done" > done.txt
""")

            # Execute with --task-output=none
            result = run_tasktree_cli(
                ["--task-output=none", "mixed-output"], cwd=project_root
            )

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify neither stdout nor stderr appear in output
            self.assertNotIn("This is stdout", result.stdout)
            self.assertNotIn("This is stderr", result.stdout)
            self.assertNotIn("This is stderr", result.stderr)

            # Verify output file was created (task still ran)
            output_file = project_root / "done.txt"
            self.assertTrue(output_file.exists(), "Output file not created")
