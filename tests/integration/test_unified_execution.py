"""Integration tests for unified script-based command execution."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


class TestUnifiedExecution(unittest.TestCase):
    """
    Test unified script-based execution for all commands.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_single_line_command_execution(self):
        """
        Test that single-line commands execute via script.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("unified_exec_single_line", project_root)

                result = self.runner.invoke(app, ["test-single"], env=self.env)

                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Command failed: {result.stdout}\n{result.stderr}",
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("Hello World", output_file.read_text())
            finally:
                os.chdir(original_cwd)

    def test_multiline_command_execution(self):
        """
        Test that multi-line commands execute via script.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("unified_exec_multiline", project_root)

                result = self.runner.invoke(app, ["test-multi"], env=self.env)

                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Command failed: {result.stdout}\n{result.stderr}",
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                content = output_file.read_text()
                self.assertIn("Line 1", content)
                self.assertIn("Line 2", content)
            finally:
                os.chdir(original_cwd)

    def test_single_line_command_with_preamble(self):
        """
        Test that preamble works with single-line commands.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("unified_exec_preamble_single_line", project_root)

                result = self.runner.invoke(app, ["test-preamble"], env=self.env)

                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Command failed: {result.stdout}\n{result.stderr}",
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                self.assertIn("from_preamble", output_file.read_text())
            finally:
                os.chdir(original_cwd)

    def test_multiline_command_with_preamble(self):
        """
        Test that preamble works with multi-line commands.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("unified_exec_preamble_multiline", project_root)

                result = self.runner.invoke(app, ["test-multi-preamble"], env=self.env)

                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Command failed: {result.stdout}\n{result.stderr}",
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created")
                content = output_file.read_text()
                self.assertIn("Start", content)
                self.assertIn("preamble_value", content)
                self.assertIn("End", content)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
