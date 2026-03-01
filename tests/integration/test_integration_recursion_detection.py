"""Integration tests for recursion detection in nested task invocations."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


class TestDirectRecursionIntegration(unittest.TestCase):
    """Integration tests for direct recursion."""

    def test_task_calls_itself_fails(self):
        """Test that a task calling itself produces recursion error."""
        with TemporaryDirectory() as tmpdir:
            copy_fixture_files("recursion_direct_self_call", Path(tmpdir))

            runner = CliRunner()
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

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("failed", result.output.lower())


class TestIndirectRecursionIntegration(unittest.TestCase):
    """Integration tests for indirect recursion."""

    def test_indirect_cycle_abc_fails(self):
        """Test that A→B→C→A cycle is detected."""
        with TemporaryDirectory() as tmpdir:
            copy_fixture_files("recursion_indirect_cycle_abc", Path(tmpdir))

            runner = CliRunner()
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

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("failed", result.output.lower())


class TestDeepChainNoCycleIntegration(unittest.TestCase):
    """Integration tests for deep chains without cycles."""

    def test_deep_no_cycle_succeeds(self):
        """Test that a deep chain (5 levels) without cycle succeeds."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "outputs"
            output_dir.mkdir()
            copy_fixture_files("recursion_deep_no_cycle", Path(tmpdir))

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

            self.assertEqual(result.exit_code, 0, f"Output: {result.output}")

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
            marker_dir = Path(tmpdir) / "markers"
            marker_dir.mkdir()
            copy_fixture_files("recursion_call_chain_accumulation", Path(tmpdir))

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

            parent_chain = (marker_dir / "parent_chain.txt").read_text().strip()
            child_chain = (marker_dir / "child_chain.txt").read_text().strip()
            grandchild_chain = (
                marker_dir / "grandchild_chain.txt"
            ).read_text().strip()

            self.assertTrue(
                parent_chain.endswith(":parent"),
                f"Expected parent_chain to end with ':parent', got: {parent_chain}",
            )

            child_pattern = r":parent,[a-f0-9]+:child$"
            self.assertIsNotNone(
                re.search(child_pattern, child_chain),
                f"Expected child_chain to end with ':parent,<hash>:child', got: {child_chain}",
            )

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
            output_dir = Path(tmpdir) / "outputs"
            output_dir.mkdir()
            copy_fixture_files("recursion_nested_call_with_deps", Path(tmpdir))

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

            self.assertTrue((output_dir / "dep.txt").exists())
            self.assertTrue((output_dir / "parent.txt").exists())
            self.assertTrue((output_dir / "child.txt").exists())


if __name__ == "__main__":
    unittest.main()
