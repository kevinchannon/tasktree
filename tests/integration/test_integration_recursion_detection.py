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
      set -e
      echo "Before recursion"
      uv run tt self-caller
      echo "After recursion"
"""
            )

            runner = CliRunner()
            # Don't set TT_CALL_CHAIN - let the natural execution build it up
            # When tt runs self-caller, it will add self-caller to the chain
            # Then when self-caller's command runs "tt self-caller" again,
            # it will detect self-caller is already in the chain

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = runner.invoke(
                    app,
                    ["self-caller"],
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

            # The task should fail when it tries to call itself
            # The nested subprocess will detect recursion and exit with non-zero,
            # causing the parent task to fail (due to set -e)
            self.assertNotEqual(result.exit_code, 0)
            # Verify the failure message indicates the task failed
            self.assertIn("failed", result.output.lower())


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
    cmd: |
      set -e
      echo "Task A"
      uv run tt task-b

  task-b:
    cmd: |
      set -e
      echo "Task B"
      uv run tt task-c

  task-c:
    cmd: |
      set -e
      echo "Task C"
      uv run tt task-a
"""
            )

            runner = CliRunner()
            # Don't set TT_CALL_CHAIN - let natural execution build it:
            # task-a runs, adds itself to chain, calls task-b
            # task-b runs, adds itself to chain, calls task-c
            # task-c runs, adds itself to chain, tries to call task-a
            # Recursion detected: task-a is already in the chain

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = runner.invoke(
                    app,
                    ["task-a"],
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

            # The task should fail when recursion is detected in the A→B→C→A cycle
            # The nested subprocess will detect recursion and exit with non-zero,
            # causing the parent task to fail (due to set -e)
            self.assertNotEqual(result.exit_code, 0)
            # Verify the failure message indicates a task failed
            self.assertIn("failed", result.output.lower())


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
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = runner.invoke(
                    app,
                    ["level-1"],
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

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
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = runner.invoke(
                    app,
                    ["parent"],
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

            self.assertEqual(result.exit_code, 0, f"Output: {result.output}")

            # Read recorded chains
            parent_chain = (marker_dir / "parent_chain.txt").read_text().strip()
            child_chain = (marker_dir / "child_chain.txt").read_text().strip()
            grandchild_chain = (
                marker_dir / "grandchild_chain.txt"
            ).read_text().strip()

            # Chain entries are now in format "cache_key:task_name"
            # Verify the chain ends with the expected pattern, regardless of any
            # pre-existing entries (e.g., when run via `uv run tt test`)

            # Parent should have itself at the end of the chain
            self.assertTrue(
                parent_chain.endswith(":parent"),
                f"Expected parent_chain to end with ':parent', got: {parent_chain}",
            )

            # Child should see parent followed by child in the chain
            # Use regex to match the pattern: ends with "hash:parent,hash:child"
            import re

            child_pattern = r":parent,[a-f0-9]+:child$"
            self.assertIsNotNone(
                re.search(child_pattern, child_chain),
                f"Expected child_chain to end with ':parent,<hash>:child', got: {child_chain}",
            )

            # Grandchild should see parent, child, grandchild in order at the end
            grandchild_pattern = r":parent,[a-f0-9]+:child,[a-f0-9]+:grandchild$"
            self.assertIsNotNone(
                re.search(grandchild_pattern, grandchild_chain),
                f"Expected grandchild_chain to end with ':parent,<hash>:child,<hash>:grandchild', got: {grandchild_chain}",
            )


class TestNestedCallWithDeps(unittest.TestCase):
    """Integration tests for nested calls combined with dependency resolution."""

    def test_nested_call_with_deps_no_cycle(self):
        """Test that task with deps that calls nested task works correctly."""
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            output_dir = Path(tmpdir) / "outputs"
            output_dir.mkdir()

            recipe_path.write_text(
                """
tasks:
  dep-task:
    outputs: [outputs/dep.txt]
    cmd: echo "Dependency" > outputs/dep.txt

  parent:
    deps: [dep-task]
    outputs: [outputs/parent.txt]
    cmd: |
      echo "Parent" > outputs/parent.txt
      tt child

  child:
    outputs: [outputs/child.txt]
    cmd: echo "Child" > outputs/child.txt
"""
            )

            runner = CliRunner()
            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = runner.invoke(
                    app,
                    ["parent"],
                    catch_exceptions=False,
                )
            finally:
                os.chdir(original_cwd)

            # Should succeed
            self.assertEqual(result.exit_code, 0, f"Output: {result.output}")

            # Verify all outputs were created
            self.assertTrue((output_dir / "dep.txt").exists())
            self.assertTrue((output_dir / "parent.txt").exists())
            self.assertTrue((output_dir / "child.txt").exists())


if __name__ == "__main__":
    unittest.main()
