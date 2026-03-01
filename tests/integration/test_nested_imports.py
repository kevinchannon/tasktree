"""Integration tests for nested imports functionality."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestNestedImports(unittest.TestCase):
    """
    Integration tests for nested import execution.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_nested_import_task_execution(self):
        """
        Test that tasks from nested imports execute correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("nested_imports_basic", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the deeply nested task: common.base.setup
                result = self.runner.invoke(app, ["common.base.setup"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Task failed: {result.stdout}")
                self.assertIn(
                    "Task 'common.base.setup' completed successfully",
                    strip_ansi_codes(result.stdout),
                )

                # Verify the output file was created
                self.assertTrue((project_root / "base-output.txt").exists())
                self.assertEqual(
                    (project_root / "base-output.txt").read_text().strip(),
                    "base setup complete",
                )

                # Run the main task which depends on nested tasks
                result = self.runner.invoke(app, ["main"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Both output files should exist
                self.assertTrue((project_root / "base-output.txt").exists())
                self.assertTrue((project_root / "common-output.txt").exists())

            finally:
                os.chdir(original_cwd)

    def test_nested_import_dependency_chain(self):
        """
        Test dependency resolution across nested imports.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("nested_imports_chain", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the final task - should trigger entire dependency chain
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Task failed: {result.stdout}")

                # Verify all files were created in the correct order
                self.assertTrue((project_root / "init.txt").exists())
                self.assertTrue((project_root / "config.txt").exists())
                self.assertTrue((project_root / "setup.txt").exists())
                self.assertTrue((project_root / "prepare.txt").exists())
                self.assertTrue((project_root / "build.txt").exists())
                self.assertTrue((project_root / "deploy.txt").exists())

                # Verify contents show correct order
                self.assertEqual(
                    (project_root / "init.txt").read_text().strip(), "step 1"
                )
                self.assertEqual(
                    (project_root / "config.txt").read_text().strip(), "step 2"
                )
                self.assertEqual(
                    (project_root / "setup.txt").read_text().strip(), "step 3"
                )
                self.assertEqual(
                    (project_root / "prepare.txt").read_text().strip(), "step 4"
                )
                self.assertEqual(
                    (project_root / "build.txt").read_text().strip(), "step 5"
                )
                self.assertEqual(
                    (project_root / "deploy.txt").read_text().strip(), "step 6"
                )

            finally:
                os.chdir(original_cwd)

    def test_diamond_import_execution(self):
        """
        Test diamond import pattern executes correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("nested_imports_diamond", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run main task - should execute both branches
                result = self.runner.invoke(app, ["main"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Task failed: {result.stdout}")

                # Both branches should have created their output files
                self.assertTrue((project_root / "left.txt").exists())
                self.assertTrue((project_root / "right.txt").exists())

                # Base setup file should exist (created once or twice, doesn't matter)
                self.assertTrue((project_root / "base-setup.txt").exists())

                # Verify each path can be executed independently
                # Clean outputs and test left path
                (project_root / "base-setup.txt").unlink()
                (project_root / "left.txt").unlink()

                result = self.runner.invoke(app, ["left.left-task"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "left.txt").exists())

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
