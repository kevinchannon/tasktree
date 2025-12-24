"""Integration tests for working_dir handling with real subprocess execution."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestWorkingDirectory(unittest.TestCase):
    """Test that tasks execute in correct working directory."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_task_executes_in_working_dir(self):
        """Test task runs in specified working_dir subdirectory."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory
            subdir = project_root / "subdir"
            subdir.mkdir()

            # Create recipe with working_dir
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    working_dir: subdir
    outputs: [output.txt]
    cmd: pwd > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify output was created in subdir (not project root)
                output_file = subdir / "output.txt"
                self.assertTrue(output_file.exists())
                self.assertFalse((project_root / "output.txt").exists())

                # Verify the pwd output shows subdir path
                pwd_output = output_file.read_text().strip()
                self.assertTrue(pwd_output.endswith("subdir"))

            finally:
                os.chdir(original_cwd)

    def test_output_paths_resolved_with_working_dir(self):
        """Test outputs are created relative to working_dir."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project subdirectory
            project_dir = project_root / "project"
            project_dir.mkdir()

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    working_dir: project
    outputs: [target/bin]
    cmd: mkdir -p target && echo binary > target/bin
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run task
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify output created in project/target/bin (not ./target/bin)
                self.assertTrue((project_dir / "target" / "bin").exists())
                self.assertFalse((project_root / "target").exists())

                # Verify content
                bin_content = (project_dir / "target" / "bin").read_text()
                self.assertEqual(bin_content.strip(), "binary")

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
