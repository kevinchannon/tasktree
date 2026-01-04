"""E2E tests for non-docker environments."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


class TestNonDockerEnvironment(unittest.TestCase):
    """Test basic task execution without Docker."""

    def test_simple_parameterized_task(self):
        """Test that parameterized task executes with default environment value."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  deploy:
    args:
      - foo
      - environment: { type: str, choices: ["dev", "staging", "prod"], default: "dev" }
    outputs: [deploy.log]
    cmd: |
      echo "environment={{ arg.environment }}" > deploy.log
      echo "foo was {{ arg.foo }}"
""")

            # Execute with positional argument and default environment
            result = run_tasktree_cli(["deploy", "42"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify output file
            output_file = project_root / "deploy.log"
            self.assertTrue(output_file.exists(), "Output file not created")
            self.assertEqual(
                output_file.read_text().strip(),
                "environment=dev"
            )

            # Verify terminal output
            self.assertIn("foo was 42", result.stdout)

    def test_parameterized_task_with_custom_environment(self):
        """Test that parameterized task executes with explicit environment value."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  deploy:
    args:
      - foo
      - environment: { type: str, choices: ["dev", "staging", "prod"], default: "dev" }
    outputs: [deploy.log]
    cmd: |
      echo "environment={{ arg.environment }}" > deploy.log
      echo "foo was {{ arg.foo }}"
""")

            # Execute with both arguments
            result = run_tasktree_cli(["deploy", "42", "environment=prod"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify output file
            output_file = project_root / "deploy.log"
            self.assertTrue(output_file.exists(), "Output file not created")
            self.assertEqual(
                output_file.read_text().strip(),
                "environment=prod"
            )

            # Verify terminal output
            self.assertIn("foo was 42", result.stdout)

    def test_list_tasks_output(self):
        """Test that --list displays tasks with correct formatting."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parameterized task
            (project_root / "tasktree.yaml").write_text("""
tasks:
  deploy:
    desc: Deploy to environment
    args:
      - foo
      - environment: { type: str, choices: ["dev", "staging", "prod"], default: "dev" }
    outputs: [deploy.log]
    cmd: |
      echo "environment={{ arg.environment }}" > deploy.log
      echo "foo was {{ arg.foo }}"
""")

            # Execute --list
            result = run_tasktree_cli(["--list"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify task name is in output
            self.assertIn("deploy", result.stdout)

            # Verify description is in output
            self.assertIn("Deploy to environment", result.stdout)

            # Verify arguments are shown (the actual format includes ANSI codes, so we check for the argument names)
            self.assertIn("foo", result.stdout)
            self.assertIn("environment", result.stdout)


if __name__ == "__main__":
    unittest.main()
