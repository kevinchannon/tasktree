"""Integration tests for configuration file hierarchy.

Tests the full 7-level configuration hierarchy:
1. CLI --runner flag
2. Task's run_in field
3. Recipe's default_runner
4. Project config (.tasktree-config.yml)
5. User config
6. Machine config
7. Platform default
"""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestConfigHierarchy(unittest.TestCase):
    """Test configuration file hierarchy and precedence."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_project_config_overrides_platform_default(self):
        """Test that project config (.tasktree-config.yml) overrides platform default."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project config
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: |
      echo "PROJECT CONFIG"
""")

            # Create tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello from test"
""")

            # Run task and verify project config was used
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)
            finally:
                os.chdir(original_cwd)

            # Should see the project config preamble
            self.assertIn("PROJECT CONFIG", output)
            self.assertEqual(result.exit_code, 0)

    def test_recipe_default_runner_overrides_project_config(self):
        """Test that recipe default runner overrides project config."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project config with one preamble
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "PROJECT CONFIG"
""")

            # Create tasktree.yaml with different default runner
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  default: custom
  custom:
    shell: bash
    preamble: echo "RECIPE DEFAULT"

tasks:
  test:
    cmd: echo "Hello"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Should see recipe default, not project config
                self.assertIn("RECIPE DEFAULT", output)
                self.assertNotIn("PROJECT CONFIG", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    def test_task_run_in_overrides_all_configs(self):
        """Test that task's run_in field overrides all config levels."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project config
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "PROJECT CONFIG"
""")

            # Create tasktree.yaml with task-specific runner
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  default: custom
  custom:
    shell: bash
    preamble: echo "RECIPE DEFAULT"

  task-specific:
    shell: bash
    preamble: echo "TASK SPECIFIC"

tasks:
  test:
    run_in: task-specific
    cmd: echo "Hello"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Should see task-specific runner only
            finally:
                os.chdir(original_cwd)
            self.assertIn("TASK SPECIFIC", output)
            self.assertNotIn("RECIPE DEFAULT", output)
            self.assertNotIn("PROJECT CONFIG", output)
            self.assertEqual(result.exit_code, 0)

    def test_empty_project_config_falls_back_to_platform_default(self):
        """Test that empty project config falls back to platform default."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create empty project config
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("")

            # Create tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            # Should not crash, should use platform default
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                self.assertIn("Hello", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    @patch("tasktree.config.get_user_config_path")
    def test_user_config_overrides_platform_default(self, mock_user_config):
        """Test that user config overrides platform default."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            user_config_dir = Path(tmpdir) / "user_config"
            user_config_dir.mkdir()

            # Create user config
            user_config_file = user_config_dir / "config.yml"
            user_config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "USER CONFIG"
""")
            mock_user_config.return_value = user_config_file

            # Create tasktree.yaml (no project config, no recipe default)
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Should see user config preamble
                self.assertIn("USER CONFIG", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    @patch("tasktree.config.get_user_config_path")
    def test_project_config_overrides_user_config(self, mock_user_config):
        """Test that project config overrides user config."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            user_config_dir = Path(tmpdir) / "user_config"
            user_config_dir.mkdir()

            # Create user config
            user_config_file = user_config_dir / "config.yml"
            user_config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "USER CONFIG"
""")
            mock_user_config.return_value = user_config_file

            # Create project config
            project_config = project_root / ".tasktree-config.yml"
            project_config.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "PROJECT CONFIG"
""")

            # Create tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Should see project config, not user config
                self.assertIn("PROJECT CONFIG", output)
                self.assertNotIn("USER CONFIG", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    @patch("tasktree.config.get_machine_config_path")
    @patch("tasktree.config.get_user_config_path")
    def test_full_hierarchy_machine_user_project(
        self, mock_user_config, mock_machine_config
    ):
        """Test full hierarchy: machine < user < project."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_dir = Path(tmpdir) / "configs"
            config_dir.mkdir()

            # Create machine config
            machine_config_file = config_dir / "machine.yml"
            machine_config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "MACHINE CONFIG"
""")
            mock_machine_config.return_value = machine_config_file

            # Create user config
            user_config_file = config_dir / "user.yml"
            user_config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "USER CONFIG"
""")
            mock_user_config.return_value = user_config_file

            # Create project config
            project_config = project_root / ".tasktree-config.yml"
            project_config.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "PROJECT CONFIG"
""")

            # Create tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Should see project config only (highest precedence)
                self.assertIn("PROJECT CONFIG", output)
                self.assertNotIn("USER CONFIG", output)
                self.assertNotIn("MACHINE CONFIG", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    def test_project_config_discovery_walks_up_tree(self):
        """Test that project config is found by walking up directory tree."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project config at root
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("""
runners:
  default:
    shell: bash
    preamble: echo "PROJECT CONFIG"
""")

            # Create nested directory structure
            nested_dir = project_root / "subdir" / "nested"
            nested_dir.mkdir(parents=True)

            # Create tasktree.yaml in nested directory
            recipe_file = nested_dir / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            # Run from nested directory
            original_cwd = os.getcwd()
            try:
                os.chdir(nested_dir)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Should find project config by walking up
                self.assertIn("PROJECT CONFIG", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    def test_invalid_config_falls_back_gracefully(self):
        """Test that invalid config falls back to platform default."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create invalid project config (multiple runners)
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("""
runners:
  default:
    shell: bash

  another:
    shell: bash
""")

            # Create tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            # Should not crash, should fall back to platform default
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                # Task should still execute with platform default
                self.assertIn("Hello", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)

    def test_config_with_no_runners_key_is_valid(self):
        """Test that config file with no 'runners' key is valid and ignored."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create config with no runners key
            config_file = project_root / ".tasktree-config.yml"
            config_file.write_text("""
# This is a valid but empty config
some_other_key: value
""")

            # Create tasktree.yaml
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  test:
    cmd: echo "Hello"
""")

            # Should not crash, should use platform default
            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)
                result = self.runner.invoke(app, ["test"], env=self.env)
                output = strip_ansi_codes(result.stdout)

                self.assertIn("Hello", output)
                self.assertEqual(result.exit_code, 0)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
