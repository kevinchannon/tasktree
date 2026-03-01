"""Integration tests for importing variables and runners from imported files."""

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


class TestMultiLevelImportVariablesAndRunners(unittest.TestCase):
    """Integration tests for multi-level import of variables and runners."""

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_three_level_import_resolves_variables_and_runners(self):
        """Test 3-level import chain: root -> l2 -> l3 with variables and runners."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("imported_vars_three_level", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the deeply nested task directly
                result = self.runner.invoke(app, ["l2.l3.greet"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("hello from level3", stripped)

                # Clear state so tasks re-run
                state_file = project_root / ".tasktree-state"
                if state_file.exists():
                    state_file.unlink()

                # Run the root task which traverses the full chain
                result = self.runner.invoke(app, ["all"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("hello from level3", stripped)
                self.assertIn("level2 done", stripped)
                self.assertIn("all done", stripped)

            finally:
                os.chdir(original_cwd)

    def test_imported_variable_used_in_root_task_via_namespace(self):
        """Test that root tasks can reference imported variables with full namespace."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("imported_vars_namespace", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(
                    app, ["show_version"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("version is 1.2.3", stripped)

            finally:
                os.chdir(original_cwd)

    def test_chained_variables_resolve_across_import(self):
        """Test that chained variable references within imported files resolve correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("imported_vars_chained", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(
                    app, ["build.install"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("installing to /opt/myapp", stripped)

            finally:
                os.chdir(original_cwd)

    def test_diamond_import_variables_and_runners(self):
        """Test diamond pattern: root -> {left, right} -> base with variables and runners."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("imported_vars_diamond", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run left side of the diamond
                result = self.runner.invoke(
                    app, ["left.base.hello"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("from base", stripped)

                # Clear state
                state_file = project_root / ".tasktree-state"
                if state_file.exists():
                    state_file.unlink()

                # Run right side of the diamond
                result = self.runner.invoke(
                    app, ["right.base.hello"], env=self.env
                )
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("from base", stripped)

                # Clear state
                if state_file.exists():
                    state_file.unlink()

                # Run the root which depends on both sides
                result = self.runner.invoke(app, ["all"], env=self.env)
                stripped = strip_ansi_codes(result.stdout)
                self.assertEqual(result.exit_code, 0, f"Task failed: {stripped}")
                self.assertIn("left done", stripped)
                self.assertIn("right done", stripped)
                self.assertIn("all done", stripped)

            finally:
                os.chdir(original_cwd)

    def test_cyclic_variable_references_across_imports(self):
        """Test that cyclic variable references across imports are properly handled."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("imported_vars_cyclic", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Should fail because imported file's reference to root_var gets rewritten
                # to imp.root_var, which doesn't exist
                result = self.runner.invoke(app, ["root_task"], env=self.env)
                self.assertNotEqual(result.exit_code, 0)
                # Check for error about undefined variable
                self.assertIn("not defined", result.stdout.lower())

            finally:
                os.chdir(original_cwd)

    def test_dockerfile_path_resolution_in_imported_files(self):
        """
        Test documenting current Dockerfile path resolution behavior in imported files.

        CURRENT BEHAVIOR: Dockerfile paths are resolved relative to project root,
        not relative to the imported file. This test documents this limitation.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            copy_fixture_files("imported_vars_dockerfile_path", project_root)

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # With Dockerfile at root, this should work (or fail only due to Docker unavailability)
                result = self.runner.invoke(app, ["main"], env=self.env)

                # The test should either pass (if Docker is available) or fail with
                # a Docker-related error (not a file-not-found error)
                if result.exit_code != 0:
                    # If it fails, it should be due to Docker not being available,
                    # not due to Dockerfile path resolution issues
                    self.assertNotIn("no such file", result.stdout.lower())
                    self.assertNotIn("dockerfile not found", result.stdout.lower())
                else:
                    # If Docker is available, the task should succeed
                    self.assertIn("Main task done", result.stdout)

            finally:
                os.chdir(original_cwd)
