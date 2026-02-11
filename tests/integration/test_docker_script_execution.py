"""Integration tests for Docker script execution with TempScript."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from helpers.docker import is_docker_available
from tasktree.cli import app


class TestDockerScriptExecution(unittest.TestCase):
    """
    Test Docker script execution with TempScript context manager.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    @unittest.skipUnless(is_docker_available(), "Docker not available")
    def test_docker_executes_script_with_preamble(self):
        """
        Test that Docker execution includes preamble in the script.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create output directory
            (project_root / "output").mkdir()

            # Create Dockerfile
            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""FROM alpine:latest
WORKDIR /workspace
""")

            # Create recipe with preamble
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  default: builder
  builder:
    dockerfile: ./Dockerfile
    context: .
    shell: /bin/sh
    preamble: |
      set -euo pipefail
      echo "Preamble executed" > output/preamble.txt
    volumes: ["./output:/workspace/output"]

tasks:
  test-preamble:
    run_in: builder
    outputs: [output/preamble.txt, output/result.txt]
    cmd: echo "Command executed" > output/result.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the task
                result = self.runner.invoke(app, ["test-preamble"], env=self.env)

                self.assertEqual(result.exit_code, 0, f"Task failed:\n{result.stdout}\n{result.stderr}")

                # Verify preamble was executed
                preamble_output = project_root / "output" / "preamble.txt"
                self.assertTrue(preamble_output.exists(), "Preamble should create output file")
                self.assertIn("Preamble executed", preamble_output.read_text())

                # Verify command was executed
                result_output = project_root / "output" / "result.txt"
                self.assertTrue(result_output.exists(), "Command should create output file")
                self.assertIn("Command executed", result_output.read_text())

            finally:
                os.chdir(original_cwd)

    @unittest.skipUnless(is_docker_available(), "Docker not available")
    def test_docker_executes_with_shell_args(self):
        """
        Test that Docker execution passes shell args correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create output directory
            (project_root / "output").mkdir()

            # Create Dockerfile
            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""FROM alpine:latest
WORKDIR /workspace
""")

            # Create recipe with shell args
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  default: builder
  builder:
    dockerfile: ./Dockerfile
    context: .
    shell: /bin/sh
    args: ["-e"]  # Exit on error
    volumes: ["./output:/workspace/output"]

tasks:
  test-shell-args:
    run_in: builder
    outputs: [output/success.txt]
    cmd: |
      # This should fail if -e is not set (since false returns 1)
      echo "Before error" > output/before.txt
      true
      echo "After true" > output/success.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the task
                result = self.runner.invoke(app, ["test-shell-args"], env=self.env)

                self.assertEqual(result.exit_code, 0, f"Task failed:\n{result.stdout}\n{result.stderr}")

                # Verify all commands executed
                success_output = project_root / "output" / "success.txt"
                self.assertTrue(success_output.exists(), "Command should complete successfully")

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
