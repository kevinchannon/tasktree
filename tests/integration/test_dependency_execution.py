"""Integration tests for dependency execution chains."""

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


class TestDependencyExecution(unittest.TestCase):
    """Test that dependency chains execute correctly end-to-end."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_linear_dependency_execution(self):
        """Test linear chain executes in correct order: lint -> build -> test."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with linear dependency chain
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
lint:
  outputs: [lint.log]
  cmd: echo "linting..." > lint.log

build:
  deps: [lint]
  outputs: [build.log]
  cmd: echo "building..." > build.log

test:
  deps: [build]
  outputs: [test.log]
  cmd: echo "testing..." > test.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - all three should execute in order
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs were created
                self.assertTrue((project_root / "lint.log").exists())
                self.assertTrue((project_root / "build.log").exists())
                self.assertTrue((project_root / "test.log").exists())

                # Verify execution order by checking file modification times
                lint_time = (project_root / "lint.log").stat().st_mtime
                build_time = (project_root / "build.log").stat().st_mtime
                test_time = (project_root / "test.log").stat().st_mtime

                # lint should run before build, build before test
                self.assertLessEqual(lint_time, build_time)
                self.assertLessEqual(build_time, test_time)

                # Second run - all should skip (fresh)
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

            finally:
                os.chdir(original_cwd)

    def test_diamond_dependency_execution(self):
        """Test diamond pattern: setup -> (build, test) -> deploy runs shared dep once."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with diamond dependency
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
setup:
  outputs: [setup.log]
  cmd: echo "setup" > setup.log

build:
  deps: [setup]
  outputs: [build.log]
  cmd: echo "build" > build.log

test:
  deps: [setup]
  outputs: [test.log]
  cmd: echo "test" > test.log

deploy:
  deps: [build, test]
  outputs: [deploy.log]
  cmd: echo "deploy" > deploy.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run deploy - should execute all tasks
                result = self.runner.invoke(app, ["deploy"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created
                self.assertTrue((project_root / "setup.log").exists())
                self.assertTrue((project_root / "build.log").exists())
                self.assertTrue((project_root / "test.log").exists())
                self.assertTrue((project_root / "deploy.log").exists())

                # Verify setup ran only once by checking its output contains single "setup" line
                setup_content = (project_root / "setup.log").read_text()
                self.assertEqual(setup_content.strip(), "setup")

                # Verify execution order
                setup_time = (project_root / "setup.log").stat().st_mtime
                build_time = (project_root / "build.log").stat().st_mtime
                test_time = (project_root / "test.log").stat().st_mtime
                deploy_time = (project_root / "deploy.log").stat().st_mtime

                # setup before build and test
                self.assertLessEqual(setup_time, build_time)
                self.assertLessEqual(setup_time, test_time)
                # build and test before deploy
                self.assertLessEqual(build_time, deploy_time)
                self.assertLessEqual(test_time, deploy_time)

            finally:
                os.chdir(original_cwd)

    def test_dependency_triggered_rerun(self):
        """Test modifying dependency input triggers dependent tasks."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input file for gen-config
            config_input = project_root / "config.template"
            config_input.write_text("config template")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
gen-config:
  inputs: [config.template]
  outputs: [config.json]
  cmd: echo "generated config" > config.json

build:
  deps: [gen-config]
  outputs: [app.bin]
  cmd: echo "built app" > app.bin
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - both tasks execute
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "config.json").exists())
                self.assertTrue((project_root / "app.bin").exists())

                # Record modification times
                config_time_1 = (project_root / "config.json").stat().st_mtime
                app_time_1 = (project_root / "app.bin").stat().st_mtime

                # Second run - both skip (fresh)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Times should be unchanged (tasks were skipped)
                config_time_2 = (project_root / "config.json").stat().st_mtime
                app_time_2 = (project_root / "app.bin").stat().st_mtime
                self.assertEqual(config_time_1, config_time_2)
                self.assertEqual(app_time_1, app_time_2)

                # Modify gen-config's input
                time.sleep(0.01)  # Ensure mtime changes
                config_input.write_text("modified template")

                # Third run - gen-config runs (input changed), build triggered (dependency ran)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Times should be updated (tasks executed)
                config_time_3 = (project_root / "config.json").stat().st_mtime
                app_time_3 = (project_root / "app.bin").stat().st_mtime
                self.assertGreater(config_time_3, config_time_2)
                self.assertGreater(app_time_3, app_time_2)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
