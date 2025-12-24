"""Integration tests for input change detection with real filesystem."""

import os
import re
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestInputDetection(unittest.TestCase):
    """Test that input file changes are detected correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_input_file_mtime_triggers_rerun(self):
        """Test file mtime change is detected and triggers rerun."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input file
            input_file = project_root / "input.txt"
            input_file.write_text("version 1")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: [input.txt]
    outputs: [output.txt]
    cmd: cat input.txt > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task executes
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "output.txt").exists())
                output_time_1 = (project_root / "output.txt").stat().st_mtime

                # Second run - task skips (nothing changed)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.txt").stat().st_mtime
                self.assertEqual(output_time_1, output_time_2)  # Not modified

                # Modify input file (change mtime)
                time.sleep(0.01)  # Ensure mtime changes
                input_file.write_text("version 2")

                # Third run - task executes (input changed)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_3 = (project_root / "output.txt").stat().st_mtime
                self.assertGreater(output_time_3, output_time_2)  # Was modified

                # Verify output reflects new input
                output_content = (project_root / "output.txt").read_text()
                self.assertEqual(output_content.strip(), "version 2")

            finally:
                os.chdir(original_cwd)

    def test_input_glob_pattern_detects_new_files(self):
        """Test glob pattern matches new files and triggers rerun."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create src directory with one file
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "file1.rs").write_text("fn main() {}")

            # Create recipe with glob pattern
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: [src/*.rs]
    outputs: [output.bin]
    cmd: echo "compiled" > output.bin
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task executes
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "output.bin").exists())
                output_time_1 = (project_root / "output.bin").stat().st_mtime

                # Second run - task skips (nothing changed)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.bin").stat().st_mtime
                self.assertEqual(output_time_1, output_time_2)

                # Add new file matching glob pattern
                time.sleep(0.01)  # Ensure mtime changes
                (src_dir / "file2.rs").write_text("fn test() {}")

                # Third run - task executes (new file in glob pattern)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_3 = (project_root / "output.bin").stat().st_mtime
                self.assertGreater(output_time_3, output_time_2)

            finally:
                os.chdir(original_cwd)

    def test_input_modified_file_triggers_rerun_with_glob(self):
        """Test modifying one of multiple glob-matched files triggers rerun."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create src directory with two files
            src_dir = project_root / "src"
            src_dir.mkdir()
            file1 = src_dir / "file1.rs"
            file2 = src_dir / "file2.rs"
            file1.write_text("fn main() {}")
            file2.write_text("fn test() {}")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: [src/*.rs]
    outputs: [output.bin]
    cmd: echo "compiled" > output.bin
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task executes with both files
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_1 = (project_root / "output.bin").stat().st_mtime

                # Second run - task skips
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.bin").stat().st_mtime
                self.assertEqual(output_time_1, output_time_2)

                # Modify one of the files
                time.sleep(0.01)  # Ensure mtime changes
                file1.write_text("fn main() { println!(\"modified\"); }")

                # Third run - task executes (file modified)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_3 = (project_root / "output.bin").stat().st_mtime
                self.assertGreater(output_time_3, output_time_2)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
