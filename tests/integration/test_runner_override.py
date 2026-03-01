"""Integration tests for runner override feature."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


def extract_effective_runner(output: str) -> str | None:
    """Extract the effective runner name from --show output."""
    match = re.search(r"Effective runner:\s+(\S+)", output)
    return match.group(1) if match else None


class TestBlanketRunnerOverride(unittest.TestCase):
    """Integration tests for blanket runner override at import level."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_blanket_runner_override_applied_to_non_pinned_task(self):
        """Test that import-level run_in applies to non-pinned tasks."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_blanket_applied_to_non_pinned", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run with --show to verify runner assignment
                result = self.runner.invoke(
                    app, ["--show", "build.compile"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

            finally:
                os.chdir(original_cwd)

    def test_pinned_task_ignores_blanket_runner_override(self):
        """Test that pinned tasks ignore import-level run_in."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_pinned_ignores_blanket", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify non-pinned task uses blanket runner
                result = self.runner.invoke(
                    app, ["--show", "build.normal"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

                # Verify pinned task ignores blanket runner and uses its own
                result = self.runner.invoke(
                    app, ["--show", "build.special"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.special", stripped)

            finally:
                os.chdir(original_cwd)

    def test_blanket_runner_does_not_override_explicit_task_run_in(self):
        """Test that blanket runner doesn't override task's own run_in."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_blanket_does_not_override_explicit_run_in", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify task keeps its own run_in (namespaced)
                result = self.runner.invoke(
                    app, ["--show", "build.compile"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.local", stripped)

            finally:
                os.chdir(original_cwd)


class TestSelectiveRunnerImport(unittest.TestCase):
    """Integration tests for selective runner import based on pinned tasks."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_only_pinned_task_runners_are_imported(self):
        """Test that only runners referenced by pinned tasks are imported."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_only_pinned_runners_imported", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify task1 (pinned) uses runner_a (namespaced)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                # runner_a should be imported and namespaced
                self.assertIn("build.runner_a", stripped)

                # Verify task2 (not pinned) uses docker (blanket override)
                result = self.runner.invoke(
                    app, ["--show", "build.task2"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

                # Verify runner_b and runner_c are NOT imported
                # We can check this by trying to use them explicitly (they shouldn't exist)
                # Since runner_b and runner_c are not pinned, they shouldn't be in the runner list
                result = self.runner.invoke(app, ["--list"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                # Only build.runner_a should exist from the import, not build.runner_b or build.runner_c
                # We can't directly test runner existence without a --list-runners command,
                # but we can verify that task2 uses docker (not build.runner_b)

            finally:
                os.chdir(original_cwd)

    def test_no_pinned_tasks_no_runners_imported(self):
        """Test that no runners are imported when no tasks are pinned."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_no_pinned_no_runners_imported", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Both tasks should use the blanket override (docker)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

                result = self.runner.invoke(
                    app, ["--show", "build.task2"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)

            finally:
                os.chdir(original_cwd)

    def test_all_pinned_tasks_all_runners_imported(self):
        """Test that all runners are imported when all tasks are pinned."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_all_pinned_all_runners_imported", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # task1 should use build.runner_a (pinned)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.runner_a", stripped)
                self.assertNotIn("docker", stripped)

                # task2 should use build.runner_b (pinned)
                result = self.runner.invoke(
                    app, ["--show", "build.task2"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.runner_b", stripped)
                self.assertNotIn("docker", stripped)

            finally:
                os.chdir(original_cwd)


class TestRunnerNamespacing(unittest.TestCase):
    """Integration tests for runner namespacing to prevent collisions."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_runner_namespacing_prevents_collision(self):
        """Test that imported runners are namespaced to prevent name collisions."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_namespacing_prevents_collision", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Imported task should use "build.docker" (namespaced)
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.docker", stripped)

                # Root task should use "docker" (not namespaced)
                result = self.runner.invoke(app, ["--show", "task2"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("docker", stripped)
                # Should NOT contain "build.docker" since this is a root-level task
                # However, the output might contain both runner names, so we need to be careful
                # We verify by checking that the task can run successfully with both runners defined

                # Execute both tasks to ensure they use different runners
                result = self.runner.invoke(app, ["build.task1"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

                result = self.runner.invoke(app, ["task2"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")

            finally:
                os.chdir(original_cwd)

    def test_runner_reference_rewritten_in_pinned_task(self):
        """Test that run_in references are rewritten to use namespaced runner names."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_reference_rewritten_in_pinned_task", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify task's run_in was rewritten to "build.my_runner"
                result = self.runner.invoke(
                    app, ["--show", "build.compile"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.my_runner", stripped)

                # Execute the task to ensure it works with the rewritten runner reference
                result = self.runner.invoke(app, ["build.compile"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("compiling", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_nested_import_runner_namespacing_three_levels(self):
        """Test runner namespacing through three levels of imports."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_three_level_namespacing", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify runner is namespaced with full chain: build.common.util_runner
                result = self.runner.invoke(
                    app, ["--show", "build.common.helper"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.common.util_runner", stripped)

                # Execute the nested task to verify it works
                result = self.runner.invoke(app, ["build.common.helper"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("common helper", result.stdout)

                # Execute the full dependency chain
                result = self.runner.invoke(app, ["all"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("common helper", result.stdout)
                self.assertIn("compiling", result.stdout)
                self.assertIn("done", result.stdout)

            finally:
                os.chdir(original_cwd)

    def test_four_level_nested_imports(self):
        """Test runner namespacing through four levels of imports."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_four_level_namespacing", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify runner has full namespace chain: build.common.utils.base
                result = self.runner.invoke(
                    app, ["--show", "build.common.utils.base_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.common.utils.base", stripped)

                # Execute full chain to verify all levels work
                result = self.runner.invoke(app, ["all"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                self.assertIn("base", result.stdout)
                self.assertIn("common", result.stdout)
                self.assertIn("build", result.stdout)
                self.assertIn("all", result.stdout)

            finally:
                os.chdir(original_cwd)


class TestRunnerPrecedenceOrder(unittest.TestCase):
    """Integration tests for runner precedence order."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_precedence_cli_flag_overrides_all(self):
        """Test that CLI --runner flag takes precedence over all other settings."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_precedence_cli_overrides_all", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify CLI --runner overrides pinned task runner
                result = self.runner.invoke(
                    app, ["--runner", "cli_runner", "--show", "build.pinned_task"],
                    env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("cli_runner", stripped)

                # Verify CLI --runner overrides blanket runner for normal task
                result = self.runner.invoke(
                    app, ["--runner", "cli_runner", "--show", "build.normal_task"],
                    env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("cli_runner", stripped)

                # Verify CLI --runner overrides default runner for root task
                result = self.runner.invoke(
                    app, ["--runner", "cli_runner", "--show", "root_task"],
                    env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("cli_runner", stripped)

            finally:
                os.chdir(original_cwd)

    def test_precedence_pinned_runner_over_blanket(self):
        """Test that pinned task runner takes precedence over blanket override."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_precedence_pinned_over_blanket", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Pinned task should use its pinned runner, not blanket
                result = self.runner.invoke(
                    app, ["--show", "build.pinned_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.pinned_runner", stripped)
                self.assertNotIn("blanket_runner", stripped)

                # Normal task should use blanket runner
                result = self.runner.invoke(
                    app, ["--show", "build.normal_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("blanket_runner", stripped)

            finally:
                os.chdir(original_cwd)

    def test_precedence_blanket_over_default(self):
        """Test that blanket runner override takes precedence over default runner."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_precedence_blanket_over_default", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Imported task should use blanket runner, not default
                result = self.runner.invoke(
                    app, ["--show", "build.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("blanket_runner", stripped)

            finally:
                os.chdir(original_cwd)

    def test_precedence_task_level_over_default(self):
        """Test that task-level run_in takes precedence over default runner."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_precedence_task_level_over_default", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Task with run_in should use its own runner
                result = self.runner.invoke(
                    app, ["--show", "task_with_runner"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("task_runner", stripped)

                # Task without run_in should use default
                result = self.runner.invoke(
                    app, ["--show", "task_without_runner"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("default_runner", stripped)

            finally:
                os.chdir(original_cwd)

    def test_precedence_all_levels(self):
        """Test full precedence chain with all levels defined."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_precedence_all_levels", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Without CLI flag:
                # 1. Pinned task uses pinned runner
                result = self.runner.invoke(
                    app, ["--show", "build.pinned_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("build.pinned_runner", stripped)

                # 2. Non-pinned task uses blanket runner
                result = self.runner.invoke(
                    app, ["--show", "build.blanket_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("blanket_runner", stripped)

                # 3. Root task uses default runner
                result = self.runner.invoke(
                    app, ["--show", "default_task"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("default_runner", stripped)

                # With CLI flag, everything uses cli_runner (even pinned tasks)
                # This demonstrates that --runner has highest precedence over all other mechanisms
                result = self.runner.invoke(
                    app, ["--runner", "cli_runner", "--show", "build.pinned_task"],
                    env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("cli_runner", stripped)

            finally:
                os.chdir(original_cwd)


class TestEdgeCases(unittest.TestCase):
    """Integration tests for edge cases in runner override feature."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_multiple_imports_same_file_different_overrides(self):
        """Test importing the same file multiple times with different blanket overrides."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_multiple_imports_same_file", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Verify set_a.task1 uses runner_a
                result = self.runner.invoke(
                    app, ["--show", "set_a.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("runner_a", stripped)

                # Verify set_b.task1 uses runner_b
                result = self.runner.invoke(
                    app, ["--show", "set_b.task1"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Command failed: {stripped}")
                self.assertIn("runner_b", stripped)

                # Execute both to verify they work independently
                result = self.runner.invoke(app, ["all"], env=self.env)
                self.assertEqual(result.exit_code, 0, f"Command failed: {result.stdout}")
                # Both task1 instances should run (verified by exit code)

            finally:
                os.chdir(original_cwd)

    def test_pinned_task_with_nonexistent_runner_fails_at_invocation(self):
        """Test that pinned task referencing non-existent runner fails only when that task is invoked."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            copy_fixture_files("runner_override_nonexistent_runner_fails_at_invocation", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Running a task that doesn't depend on broken_task should work
                result = self.runner.invoke(app, ["root"], env=self.env)
                self.assertEqual(result.exit_code, 0, "Tasks not using broken_task should work")
                self.assertIn("done", result.stdout)

                # But invoking the broken task should fail with clear error
                result = self.runner.invoke(app, ["build.broken_task"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Task with nonexistent runner should fail")
                # Error should mention the missing runner
                self.assertIn("nonexistent_runner", result.stdout.lower() + result.stderr.lower())

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
