"""Integration tests for recursion detection in nested task invocations."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class TestDirectRecursionIntegration(unittest.TestCase):
    """Integration tests for direct recursion."""

    def test_task_calls_itself_fails(self):
        """Test that a task calling itself produces recursion error."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  self-caller:
    cmd: |
      echo "Before recursion"
      tt self-caller
      echo "After recursion"
"""
            )

            runner = CliRunner()
            # Must set TT_CALL_CHAIN to simulate we're already running this task
            # (In real execution, the first invocation would set this before calling itself)
            env = os.environ.copy()
            env["TT_CALL_CHAIN"] = "self-caller"

            result = runner.invoke(
                app,
                ["self-caller"],
                catch_exceptions=False,
                env=env,
                obj={"config_path": recipe_path},
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Recursion detected", result.output)
            self.assertIn("self-caller", result.output)


class TestIndirectRecursionIntegration(unittest.TestCase):
    """Integration tests for indirect recursion."""

    def test_indirect_cycle_abc_fails(self):
        """Test that A→B→C→A cycle is detected."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  task-a:
    cmd: echo "Task A" && tt task-b

  task-b:
    cmd: echo "Task B" && tt task-c

  task-c:
    cmd: echo "Task C" && tt task-a
"""
            )

            runner = CliRunner()
            # Simulate: task-a → task-b → task-c, now task-c tries to call task-a
            env = os.environ.copy()
            env["TT_CALL_CHAIN"] = "task-a,task-b,task-c"

            result = runner.invoke(
                app,
                ["task-a"],
                catch_exceptions=False,
                env=env,
                obj={"config_path": recipe_path},
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Recursion detected", result.output)
            self.assertIn("task-a", result.output)


class TestDeepChainNoCycleIntegration(unittest.TestCase):
    """Integration tests for deep chains without cycles."""

    def test_deep_no_cycle_succeeds(self):
        """Test that a deep chain (5 levels) without cycle succeeds."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            output_dir = Path(tmpdir) / "outputs"
            output_dir.mkdir()

            recipe_path.write_text(
                f"""
tasks:
  level-1:
    outputs: [{output_dir}/level1.txt]
    cmd: |
      echo "Level 1" > {output_dir}/level1.txt
      tt level-2

  level-2:
    outputs: [{output_dir}/level2.txt]
    cmd: |
      echo "Level 2" > {output_dir}/level2.txt
      tt level-3

  level-3:
    outputs: [{output_dir}/level3.txt]
    cmd: |
      echo "Level 3" > {output_dir}/level3.txt
      tt level-4

  level-4:
    outputs: [{output_dir}/level4.txt]
    cmd: |
      echo "Level 4" > {output_dir}/level4.txt
      tt level-5

  level-5:
    outputs: [{output_dir}/level5.txt]
    cmd: echo "Level 5" > {output_dir}/level5.txt
"""
            )

            runner = CliRunner()
            result = runner.invoke(
                app,
                ["level-1"],
                catch_exceptions=False,
                obj={"config_path": recipe_path},
            )

            # Should succeed
            self.assertEqual(result.exit_code, 0, f"Output: {result.output}")

            # Verify all outputs were created
            for i in range(1, 6):
                output_file = output_dir / f"level{i}.txt"
                self.assertTrue(
                    output_file.exists(), f"Output file {output_file} should exist"
                )


class TestCallChainAccumulation(unittest.TestCase):
    """Integration tests for call chain accumulation across levels."""

    def test_call_chain_accumulates_across_levels(self):
        """Test that TT_CALL_CHAIN correctly accumulates across nesting levels."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            marker_dir = Path(tmpdir) / "markers"
            marker_dir.mkdir()

            # Create tasks that record their call chain to files
            recipe_path.write_text(
                f"""
tasks:
  parent:
    cmd: |
      echo "$TT_CALL_CHAIN" > {marker_dir}/parent_chain.txt
      tt child

  child:
    cmd: |
      echo "$TT_CALL_CHAIN" > {marker_dir}/child_chain.txt
      tt grandchild

  grandchild:
    cmd: echo "$TT_CALL_CHAIN" > {marker_dir}/grandchild_chain.txt
"""
            )

            runner = CliRunner()
            result = runner.invoke(
                app,
                ["parent"],
                catch_exceptions=False,
                obj={"config_path": recipe_path},
            )

            self.assertEqual(result.exit_code, 0, f"Output: {result.output}")

            # Read recorded chains
            parent_chain = (marker_dir / "parent_chain.txt").read_text().strip()
            child_chain = (marker_dir / "child_chain.txt").read_text().strip()
            grandchild_chain = (
                marker_dir / "grandchild_chain.txt"
            ).read_text().strip()

            # Parent should see empty chain (it's the top level)
            self.assertEqual(parent_chain, "")

            # Child should see parent in chain
            self.assertEqual(child_chain, "parent")

            # Grandchild should see parent,child in chain
            self.assertEqual(grandchild_chain, "parent,child")


class TestNestedCallWithDeps(unittest.TestCase):
    """Integration tests for nested calls combined with dependency resolution."""

    def test_nested_call_with_deps_no_cycle(self):
        """Test that task with deps that calls nested task works correctly."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            output_dir = Path(tmpdir) / "outputs"
            output_dir.mkdir()

            recipe_path.write_text(
                f"""
tasks:
  dep-task:
    outputs: [{output_dir}/dep.txt]
    cmd: echo "Dependency" > {output_dir}/dep.txt

  parent:
    deps: [dep-task]
    outputs: [{output_dir}/parent.txt]
    cmd: |
      echo "Parent" > {output_dir}/parent.txt
      tt child

  child:
    outputs: [{output_dir}/child.txt]
    cmd: echo "Child" > {output_dir}/child.txt
"""
            )

            runner = CliRunner()
            result = runner.invoke(
                app,
                ["parent"],
                catch_exceptions=False,
                obj={"config_path": recipe_path},
            )

            # Should succeed
            self.assertEqual(result.exit_code, 0, f"Output: {result.output}")

            # Verify all outputs were created
            self.assertTrue((output_dir / "dep.txt").exists())
            self.assertTrue((output_dir / "parent.txt").exists())
            self.assertTrue((output_dir / "child.txt").exists())


if __name__ == "__main__":
    unittest.main()
