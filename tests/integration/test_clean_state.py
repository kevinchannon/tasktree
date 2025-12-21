"""Integration tests for --clean-state option and its aliases."""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestCleanState(unittest.TestCase):
    """Test that --clean-state and its aliases work correctly."""

    def test_clean_state_removes_state_file(self):
        """Test that --clean-state removes the .tasktree-state file."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  outputs: [output.txt]
  cmd: echo "building" > output.txt
""")

            # Run a task to create state file
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "build"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)

            # Verify state file was created
            state_file = project_root / ".tasktree-state"
            self.assertTrue(state_file.exists())

            # Run --clean-state
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "--clean-state"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("Removed", result.stdout)

            # Verify state file was removed
            self.assertFalse(state_file.exists())

    def test_clean_alias_works(self):
        """Test that --clean works as an alias for --clean-state."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  outputs: [output.txt]
  cmd: echo "building" > output.txt
""")

            # Run a task to create state file
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "build"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)

            # Verify state file was created
            state_file = project_root / ".tasktree-state"
            self.assertTrue(state_file.exists())

            # Run --clean (short alias)
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "--clean"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("Removed", result.stdout)

            # Verify state file was removed
            self.assertFalse(state_file.exists())

    def test_reset_alias_works(self):
        """Test that --reset works as an alias for --clean-state."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  outputs: [output.txt]
  cmd: echo "building" > output.txt
""")

            # Run a task to create state file
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "build"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)

            # Verify state file was created
            state_file = project_root / ".tasktree-state"
            self.assertTrue(state_file.exists())

            # Run --reset
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "--reset"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("Removed", result.stdout)

            # Verify state file was removed
            self.assertFalse(state_file.exists())

    def test_clean_state_when_no_state_file(self):
        """Test that --clean-state handles missing state file gracefully."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
build:
  desc: Build task
  cmd: echo "building"
""")

            # State file doesn't exist yet
            state_file = project_root / ".tasktree-state"
            self.assertFalse(state_file.exists())

            # Run --clean-state
            result = subprocess.run(
                [sys.executable, "-m", "tasktree.cli", "--clean-state"],
                cwd=project_root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("No state file found", result.stdout)


if __name__ == "__main__":
    unittest.main()
