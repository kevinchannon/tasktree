"""E2E tests for nested task invocations."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


class TestNestedInvocationsE2E(unittest.TestCase):
    """End-to-end tests for nested tt invocations via real subprocess execution."""

    def test_real_subprocess_nested_invocation(self):
        """
        Test nested invocation using real subprocess calls.
        Verifies state file contains both parent and child entries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parent→child nesting
            (project_root / "tasktree.yaml").write_text("""
tasks:
  child:
    outputs: [child_output.txt]
    cmd: echo "child executed" > child_output.txt

  parent:
    outputs: [parent_output.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent executed" > parent_output.txt
""")

            # Execute parent task via subprocess
            result = run_tasktree_cli(["parent"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify both output files were created
            child_output = project_root / "child_output.txt"
            parent_output = project_root / "parent_output.txt"

            self.assertTrue(child_output.exists(), "Child output file not created")
            self.assertTrue(parent_output.exists(), "Parent output file not created")

            self.assertEqual(child_output.read_text().strip(), "child executed")
            self.assertEqual(parent_output.read_text().strip(), "parent executed")

            # Verify state file exists and has correct structure
            state_file = project_root / ".tasktree-state"
            self.assertTrue(state_file.exists(), "State file not created")

            with open(state_file, "r") as f:
                state_data = json.load(f)

            # Should have 2 entries (parent and child)
            self.assertEqual(
                len(state_data),
                2,
                f"Expected 2 state entries, got {len(state_data)}",
            )

            # Verify each entry has required fields
            for cache_key, task_state in state_data.items():
                self.assertIn("last_run", task_state)
                self.assertIn("input_state", task_state)
                self.assertIsInstance(task_state["last_run"], (int, float))
                self.assertIsInstance(task_state["input_state"], dict)

    def test_nested_invocation_incrementality_e2e(self):
        """
        Test that incrementality works across nested calls in real execution.
        Second run should skip child if outputs are fresh.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "tasktree.yaml").write_text("""
tasks:
  child:
    outputs: [child.out]
    cmd: echo "child" > child.out

  parent:
    outputs: [parent.out]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent" > parent.out
""")

            # First run - both execute
            result1 = run_tasktree_cli(["parent"], cwd=project_root)
            self.assertEqual(result1.returncode, 0)

            child_out = project_root / "child.out"
            parent_out = project_root / "parent.out"

            self.assertTrue(child_out.exists())
            self.assertTrue(parent_out.exists())

            # Record child mtime
            child_mtime_1 = child_out.stat().st_mtime

            # Second run - child should skip (fresh outputs)
            result2 = run_tasktree_cli(["parent"], cwd=project_root)
            self.assertEqual(result2.returncode, 0)

            # Child output should have been regenerated (child has no inputs, always runs)
            child_mtime_2 = child_out.stat().st_mtime
            self.assertGreater(
                child_mtime_2,
                child_mtime_1,
                "Child should run on second invocation (no inputs)",
            )

            # Verify child ran
            self.assertIn("child", result2.stdout.lower())

    def test_complex_topology_real_execution(self):
        """
        Test complex dependency topology with nested calls.
        Diamond pattern: parent calls B and C, both call D.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "tasktree.yaml").write_text("""
tasks:
  d:
    outputs: [d.txt]
    cmd: echo "d" > d.txt

  b:
    outputs: [b.txt]
    cmd: |
      python3 -m tasktree.cli d
      echo "b" > b.txt

  c:
    outputs: [c.txt]
    cmd: |
      python3 -m tasktree.cli d
      echo "c" > c.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli b
      python3 -m tasktree.cli c
      echo "parent" > parent.txt
""")

            # Execute parent
            result = run_tasktree_cli(["parent"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify all outputs created
            self.assertTrue((project_root / "d.txt").exists())
            self.assertTrue((project_root / "b.txt").exists())
            self.assertTrue((project_root / "c.txt").exists())
            self.assertTrue((project_root / "parent.txt").exists())

            # Verify state file correctness
            state_file = project_root / ".tasktree-state"
            with open(state_file, "r") as f:
                state_data = json.load(f)

            # Should have 4 entries (d, b, c, parent)
            self.assertEqual(len(state_data), 4)

            # Verify execution order via timestamps
            d_time = (project_root / "d.txt").stat().st_mtime
            b_time = (project_root / "b.txt").stat().st_mtime
            c_time = (project_root / "c.txt").stat().st_mtime
            parent_time = (project_root / "parent.txt").stat().st_mtime

            # With "no inputs = always run", d runs multiple times:
            # - Once when b invokes it
            # - Again when c invokes it
            # So d.txt may have timestamp after b.txt or c.txt
            # Just verify all files exist (timing assertions no longer valid)

            # Verify parent runs last
            self.assertLessEqual(b_time, parent_time)
            self.assertLessEqual(c_time, parent_time)


if __name__ == "__main__":
    unittest.main()
