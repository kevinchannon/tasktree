"""Integration tests for end-to-end CLI workflows."""

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


class TestEndToEnd(unittest.TestCase):
    """
    Test complete CLI workflows from argument parsing to execution.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_args_flow_cli_to_subprocess(self):
        """
        Test arguments flow from CLI -> parser -> executor -> subprocess.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with typed arguments
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  deploy:
    args:
      - environment
      - region: { type: str, default: us-west-1 }
      - port: { type: int, default: 8080 }
      - debug: { type: bool, default: false }
    outputs: [deploy.log]
    cmd: echo "env={{ arg.environment }} region={{ arg.region }} port={{ arg.port }} debug={{ arg.debug }}" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test 1: Positional arguments
                result = self.runner.invoke(app, ["deploy", "production"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("env=production", log_content)
                self.assertIn("region=us-west-1", log_content)  # Default value
                self.assertIn("port=8080", log_content)  # Default value
                self.assertIn("debug=false", log_content)  # Default value (lowercase)

                # Clean up for next test
                (project_root / "deploy.log").unlink()

                # Test 2: Named arguments with type conversion
                result = self.runner.invoke(
                    app,
                    [
                        "deploy",
                        "staging",
                        "region=eu-west-1",
                        "port=9000",
                        "debug=true",
                    ],
                    env=self.env,
                )
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("env=staging", log_content)
                self.assertIn("region=eu-west-1", log_content)
                self.assertIn("port=9000", log_content)  # Type converted to int
                self.assertIn(
                    "debug=true", log_content
                )  # Type converted to bool (lowercase)

                # Clean up for next test
                (project_root / "deploy.log").unlink()

                # Test 3: Mixed positional and named
                result = self.runner.invoke(
                    app, ["deploy", "production", "debug=true"], env=self.env
                )
                self.assertEqual(result.exit_code, 0)

                log_content = (project_root / "deploy.log").read_text().strip()
                self.assertIn("env=production", log_content)
                self.assertIn("region=us-west-1", log_content)  # Default
                self.assertIn("port=8080", log_content)  # Default
                self.assertIn("debug=true", log_content)  # Provided (lowercase)

            finally:
                os.chdir(original_cwd)

    def test_task_execution_failure_shows_user_friendly_error(self):
        """
        Test task failure shows error message, not Python traceback.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with failing task
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  failing-task:
    cmd: exit 42
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run failing task
                result = self.runner.invoke(app, ["failing-task"], env=self.env)

                # Should exit with non-zero code
                self.assertNotEqual(result.exit_code, 0)

                # Output should contain user-friendly error
                output = strip_ansi_codes(result.stdout)
                self.assertIn("failed", output.lower())
                self.assertIn("42", output)  # Exit code should be mentioned

                # Should NOT contain Python traceback
                self.assertNotIn("Traceback", output)
                self.assertNotIn('File "', output)

            finally:
                os.chdir(original_cwd)

    def test_task_name_with_dot_rejected(self):
        """
        Test that task names containing dots are rejected with a clear error message.

        Dots in task names are reserved for namespacing imported tasks (e.g., namespace.task),
        so user-defined task names cannot contain dots.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a recipe with a task name containing a dot
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build.release:
    cmd: echo "building"
""")

            # Change to project directory
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Try to run the task - should fail with clear error
                result = self.runner.invoke(app, ["build.release"], env=self.env)

                # Should exit with error
                self.assertNotEqual(result.exit_code, 0)

                # Error message should explain why dots are not allowed
                output = strip_ansi_codes(result.stdout)
                self.assertIn("must not contain dots", output)
                # Check for "reserved" and "namespacing" separately (they may be split across lines)
                self.assertIn("reserved", output)
                self.assertIn("namespacing", output)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
