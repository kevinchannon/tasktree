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

    def test_task_output_none_with_short_flag(self):
        """
        Test that -O none works as short form of --task-output=none.
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

            # Execute with -O none
            result = run_tasktree_cli(["-O", "none", "mixed-output"], cwd=project_root)

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

    def test_task_output_none_case_insensitive(self):
        """
        Test that --task-output accepts NONE in various cases (NONE, None, none).
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
            result = run_tasktree_cli(["--task-output=NONE", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Uppercase NONE should be accepted")

            # Test mixed case
            result = run_tasktree_cli(["--task-output=None", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Mixed case None should be accepted")

    def test_task_output_err_shows_only_stderr(self):
        """
        Test that --task-output=err shows only stderr, suppresses stdout.
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

            # Execute with --task-output=err
            result = run_tasktree_cli(
                ["--task-output=err", "mixed-output"], cwd=project_root
            )

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify stderr appears in output
            self.assertIn("This is stderr", result.stderr)

            # Verify stdout does NOT appear in output
            # (Note: stdout should be empty since it was suppressed)
            self.assertNotIn("This is stdout", result.stdout)
            self.assertNotIn("This is stdout", result.stderr)

            # Verify output file was created
            output_file = project_root / "done.txt"
            self.assertTrue(output_file.exists(), "Output file not created")

    def test_task_output_err_case_insensitive(self):
        """
        Test that --task-output accepts ERR in various cases (ERR, Err, err).
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
      echo "stderr message" >&2
      echo "done" > done.txt
""")

            # Test uppercase
            result = run_tasktree_cli(["--task-output=ERR", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Uppercase ERR should be accepted")

            # Test mixed case
            result = run_tasktree_cli(["--task-output=Err", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Mixed case Err should be accepted")

    def test_task_output_err_with_short_flag(self):
        """
        Test that -O err works as short form of --task-output=err.
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

            # Execute with -O err
            result = run_tasktree_cli(["-O", "err", "mixed-output"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify stderr appears, stdout does not
            self.assertIn("This is stderr", result.stderr)
            self.assertNotIn("This is stdout", result.stdout)
            self.assertNotIn("This is stdout", result.stderr)

    def test_task_output_on_err_suppresses_stderr_on_success(self):
        """
        Test that --task-output=on-err suppresses stderr when task succeeds.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with successful task that outputs to stderr
            (project_root / "tasktree.yaml").write_text("""
tasks:
  successful-task:
    outputs: [done.txt]
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      echo "done" > done.txt
""")

            # Execute with --task-output=on-err
            result = run_tasktree_cli(
                ["--task-output=on-err", "successful-task"], cwd=project_root
            )

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify stderr is suppressed (task succeeded)
            self.assertNotIn("This is stderr", result.stdout)
            self.assertNotIn("This is stderr", result.stderr)

            # Verify output file was created
            output_file = project_root / "done.txt"
            self.assertTrue(output_file.exists(), "Output file not created")

    def test_task_output_on_err_shows_stderr_on_failure(self):
        """
        Test that --task-output=on-err shows buffered stderr when task fails.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with failing task that outputs to stderr
            (project_root / "tasktree.yaml").write_text("""
tasks:
  failing-task:
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      exit 1
""")

            # Execute with --task-output=on-err
            result = run_tasktree_cli(
                ["--task-output=on-err", "failing-task"], cwd=project_root
            )

            # Assert failure
            self.assertNotEqual(
                result.returncode,
                0,
                "Expected task to fail but it succeeded",
            )

            # Verify stderr appears in output (task failed)
            self.assertIn("This is stderr", result.stderr)

    def test_task_output_on_err_handles_failure_with_no_stderr(self):
        """
        Test that --task-output=on-err handles failures gracefully even with no stderr.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with failing task that has no stderr output
            (project_root / "tasktree.yaml").write_text("""
tasks:
  silent-failure:
    cmd: |
      echo "This is stdout"
      exit 1
""")

            # Execute with --task-output=on-err
            result = run_tasktree_cli(
                ["--task-output=on-err", "silent-failure"], cwd=project_root
            )

            # Assert failure
            self.assertNotEqual(
                result.returncode,
                0,
                "Expected task to fail but it succeeded",
            )

            # Should not crash - just no stderr to show
            # The task error message from tasktree itself will appear

    def test_task_output_on_err_case_insensitive(self):
        """
        Test that --task-output accepts ON-ERR in various cases.
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
      echo "stderr message" >&2
      echo "done" > done.txt
""")

            # Test uppercase
            result = run_tasktree_cli(["--task-output=ON-ERR", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Uppercase ON-ERR should be accepted")

            # Test mixed case
            result = run_tasktree_cli(["--task-output=On-Err", "simple"], cwd=project_root)
            self.assertEqual(result.returncode, 0, "Mixed case On-Err should be accepted")

    def test_task_output_on_err_with_short_flag(self):
        """
        Test that -O on-err works as short form of --task-output=on-err.
        @athena: TBD
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with successful task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  successful-task:
    outputs: [done.txt]
    cmd: |
      echo "This is stdout"
      echo "This is stderr" >&2
      echo "done" > done.txt
""")

            # Execute with -O on-err
            result = run_tasktree_cli(["-O", "on-err", "successful-task"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify stderr is suppressed (task succeeded)
            self.assertNotIn("This is stderr", result.stdout)
            self.assertNotIn("This is stderr", result.stderr)
