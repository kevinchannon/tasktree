"""Integration tests for nested task invocations (Phase 1)."""

import json
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
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestNestedInvocations(unittest.TestCase):
    """Integration tests for nested tt invocations."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_simple_nested_invocation(self):
        """
        Test basic nested invocation: parent calls tt child.
        Both tasks should have state entries after execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create tasktree binary in PATH for nested calls
            # For this test, we'll use the current python module
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  child:
    outputs: [child.txt]
    cmd: echo "child output" > child.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree child
      echo "parent output" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify both outputs were created
                self.assertTrue((project_root / "child.txt").exists())
                self.assertTrue((project_root / "parent.txt").exists())

                # Verify state file exists and contains both tasks
                state_file = project_root / ".tasktree-state"
                self.assertTrue(state_file.exists())

                with open(state_file, "r") as f:
                    state = json.load(f)

                # Should have entries for both tasks
                # State keys are task hashes, so we check count
                self.assertEqual(len(state), 2, "State should have entries for parent and child")

            finally:
                os.chdir(original_cwd)

    def test_nested_invocation_incrementality(self):
        """
        Test that nested invocations benefit from incrementality.
        Run parent twice - second run should skip child if inputs unchanged.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  child:
    outputs: [child.txt]
    cmd: echo "child output" > child.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree child
      echo "parent output" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - both execute
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())

                # Record mtimes
                child_mtime_1 = child_txt.stat().st_mtime
                parent_mtime_1 = parent_txt.stat().st_mtime

                # Small delay to ensure timestamp difference
                time.sleep(0.1)

                # Second run - child should skip (outputs fresh)
                # Parent will run (no inputs, always runs)
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Parent output updated (parent always runs - no inputs)
                parent_mtime_2 = parent_txt.stat().st_mtime
                self.assertGreater(parent_mtime_2, parent_mtime_1)

                # Child output unchanged (skipped due to incrementality)
                child_mtime_2 = child_txt.stat().st_mtime
                self.assertEqual(child_mtime_2, child_mtime_1)

            finally:
                os.chdir(original_cwd)

    def test_multiple_sequential_nested_calls(self):
        """
        Test parent calling multiple children sequentially.
        All tasks should have correct state entries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  child1:
    outputs: [child1.txt]
    cmd: echo "child1" > child1.txt

  child2:
    outputs: [child2.txt]
    cmd: echo "child2" > child2.txt

  child3:
    outputs: [child3.txt]
    cmd: echo "child3" > child3.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree child1
      python3 -m tasktree child2
      python3 -m tasktree child3
      echo "parent done" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created
                self.assertTrue((project_root / "child1.txt").exists())
                self.assertTrue((project_root / "child2.txt").exists())
                self.assertTrue((project_root / "child3.txt").exists())
                self.assertTrue((project_root / "parent.txt").exists())

                # Verify state has all 4 tasks
                state_file = project_root / ".tasktree-state"
                with open(state_file, "r") as f:
                    state = json.load(f)

                self.assertEqual(len(state), 4, "State should have entries for parent and 3 children")

            finally:
                os.chdir(original_cwd)

    def test_nested_call_with_task_deps(self):
        """
        Test nested call to task that has its own dependencies.
        Dependency resolution should still work correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  dep:
    outputs: [dep.txt]
    cmd: echo "dependency" > dep.txt

  child:
    deps: [dep]
    outputs: [child.txt]
    cmd: echo "child" > child.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree child
      echo "parent" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created (dep, child, parent)
                self.assertTrue((project_root / "dep.txt").exists())
                self.assertTrue((project_root / "child.txt").exists())
                self.assertTrue((project_root / "parent.txt").exists())

                # Verify execution order via timestamps
                dep_time = (project_root / "dep.txt").stat().st_mtime
                child_time = (project_root / "child.txt").stat().st_mtime
                parent_time = (project_root / "parent.txt").stat().st_mtime

                # dep should run before child, child before parent
                self.assertLessEqual(dep_time, child_time)
                self.assertLessEqual(child_time, parent_time)

            finally:
                os.chdir(original_cwd)

    def test_deep_nesting_chain(self):
        """
        Test deeply nested chain: A calls B calls C calls D.
        All tasks should execute correctly with proper state management.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  d:
    outputs: [d.txt]
    cmd: echo "d" > d.txt

  c:
    outputs: [c.txt]
    cmd: |
      python3 -m tasktree d
      echo "c" > c.txt

  b:
    outputs: [b.txt]
    cmd: |
      python3 -m tasktree c
      echo "b" > b.txt

  a:
    outputs: [a.txt]
    cmd: |
      python3 -m tasktree b
      echo "a" > a.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run top-level task
                result = self.runner.invoke(app, ["a"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created
                self.assertTrue((project_root / "a.txt").exists())
                self.assertTrue((project_root / "b.txt").exists())
                self.assertTrue((project_root / "c.txt").exists())
                self.assertTrue((project_root / "d.txt").exists())

                # Verify state has all 4 tasks
                state_file = project_root / ".tasktree-state"
                with open(state_file, "r") as f:
                    state = json.load(f)

                self.assertEqual(len(state), 4, "State should have entries for all 4 tasks")

                # Verify execution order
                d_time = (project_root / "d.txt").stat().st_mtime
                c_time = (project_root / "c.txt").stat().st_mtime
                b_time = (project_root / "b.txt").stat().st_mtime
                a_time = (project_root / "a.txt").stat().st_mtime

                self.assertLessEqual(d_time, c_time)
                self.assertLessEqual(c_time, b_time)
                self.assertLessEqual(b_time, a_time)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
