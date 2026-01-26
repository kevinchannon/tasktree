"""Integration tests for unified script-based command execution."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class TestUnifiedExecution(unittest.TestCase):
    """
    Test unified script-based execution for all commands.
    @athena: 0d7f7aeb8f61
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_single_line_command_execution(self):
        """
        Test that single-line commands execute via script.
        @athena: 7d14b20aec8a
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                # Change to project directory
                os.chdir(project_root)

                # Create output file path
                output_file = project_root / "output.txt"

                # Create recipe with single-line command
                recipe_file = project_root / "tasktree.yaml"
                recipe_file.write_text(f"""
tasks:
  test-single:
    cmd: echo "Hello World" > {output_file}
""")

                # Run task
                result = self.runner.invoke(
                    app,
                    ["test-single"],
                    env=self.env
                )

                # Verify execution succeeded
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}\n{result.stderr}")

                # Verify output file was created
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("Hello World", output_file.read_text())
            finally:
                os.chdir(original_cwd)

    def test_multiline_command_execution(self):
        """
        Test that multi-line commands execute via script.
        @athena: ad0b468a0462
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                # Change to project directory
                os.chdir(project_root)

                # Create output file path
                output_file = project_root / "output.txt"

                # Create recipe with multi-line command
                recipe_file = project_root / "tasktree.yaml"
                recipe_file.write_text(f"""
tasks:
  test-multi:
    cmd: |
      echo "Line 1" > {output_file}
      echo "Line 2" >> {output_file}
""")

                # Run task
                result = self.runner.invoke(
                    app,
                    ["test-multi"],
                    env=self.env
                )

                # Verify execution succeeded
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}\n{result.stderr}")

                # Verify output file was created with both lines
                self.assertTrue(output_file.exists(), "Output file was not created")
                content = output_file.read_text()
                self.assertIn("Line 1", content)
                self.assertIn("Line 2", content)
            finally:
                os.chdir(original_cwd)

    def test_single_line_command_with_preamble(self):
        """
        Test that preamble works with single-line commands.
        @athena: ff510cb2a298
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                # Change to project directory
                os.chdir(project_root)

                # Create output file path
                output_file = project_root / "output.txt"

                # Create recipe with environment that has preamble
                recipe_file = project_root / "tasktree.yaml"
                recipe_file.write_text(f"""
environments:
  strict:
    shell: bash
    preamble: |
      set -e
      export TEST_VAR="from_preamble"

tasks:
  test-preamble:
    env: strict
    cmd: echo "$TEST_VAR" > {output_file}
""")

                # Run task
                result = self.runner.invoke(
                    app,
                    ["test-preamble"],
                    env=self.env
                )

                # Verify execution succeeded
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}\n{result.stderr}")

                # Verify preamble environment variable was set
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("from_preamble", output_file.read_text())
            finally:
                os.chdir(original_cwd)

    def test_multiline_command_with_preamble(self):
        """
        Test that preamble works with multi-line commands.
        @athena: 1597178b4c3a
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                # Change to project directory
                os.chdir(project_root)

                # Create output file path
                output_file = project_root / "output.txt"

                # Create recipe with environment that has preamble
                recipe_file = project_root / "tasktree.yaml"
                recipe_file.write_text(f"""
environments:
  strict:
    shell: bash
    preamble: |
      set -e
      MY_VAR="preamble_value"

tasks:
  test-multi-preamble:
    env: strict
    cmd: |
      echo "Start" > {output_file}
      echo "$MY_VAR" >> {output_file}
      echo "End" >> {output_file}
""")

                # Run task
                result = self.runner.invoke(
                    app,
                    ["test-multi-preamble"],
                    env=self.env
                )

                # Verify execution succeeded
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}\n{result.stderr}")

                # Verify preamble variable was used
                self.assertTrue(output_file.exists(), "Output file was not created")
                content = output_file.read_text()
                self.assertIn("Start", content)
                self.assertIn("preamble_value", content)
                self.assertIn("End", content)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
