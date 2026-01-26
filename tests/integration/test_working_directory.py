"""Integration tests for working_dir handling with real subprocess execution."""

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
    @athena: 90023a269128
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestWorkingDirectory(unittest.TestCase):
    """
    Test that tasks execute in correct working directory.
    @athena: 7e69e14f69b1
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_task_executes_in_working_dir(self):
        """
        Test task runs in specified working_dir subdirectory.
        @athena: 12253bd4064f
        """
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
        """
        Test outputs are created relative to working_dir.
        @athena: 36ae64514250
        """
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

    def test_default_working_dir_is_invocation_dir_not_tasks_file_dir(self):
        """
        Test that without explicit working_dir, tasks run from where tt is invoked, not where the tasks file is.
        @athena: 5988c6fff43d
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory with tasks file
            subdir = project_root / "config"
            subdir.mkdir()

            # Create tasks file in subdirectory
            tasks_file = subdir / "build.tasks"
            tasks_file.write_text("""
tasks:
  check-location:
    desc: Check where we execute from
    cmd: pwd > location.txt
""")

            original_cwd = os.getcwd()
            try:
                # Invoke tt from project root, pointing to tasks file in subdir
                os.chdir(project_root)

                result = self.runner.invoke(
                    app,
                    ["--tasks", "config/build.tasks", "check-location"],
                    env=self.env,
                )
                self.assertEqual(result.exit_code, 0)

                # Verify output was created in project root (where we invoked tt)
                # NOT in config/ (where the tasks file is)
                output_in_root = project_root / "location.txt"
                output_in_subdir = subdir / "location.txt"

                self.assertTrue(
                    output_in_root.exists(),
                    "Output should be in invocation directory (project root)",
                )
                self.assertFalse(
                    output_in_subdir.exists(),
                    "Output should NOT be in tasks file directory",
                )

                # Verify pwd shows project root path
                pwd_output = output_in_root.read_text().strip()
                self.assertEqual(Path(pwd_output).resolve(), project_root.resolve())

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
