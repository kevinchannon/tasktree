"""Integration tests for dependency execution chains."""

import os
import re
import time
import unittest
import yaml

from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.state import StateManager


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.
    @athena: 90023a269128
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class TestDependencyExecution(unittest.TestCase):
    """
    Test that dependency chains execute correctly end-to-end.
    @athena: 93e9b0c24e68
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_linear_dependency_execution(self):
        """
        Test linear chain executes in correct order: lint -> build -> test.
        @athena: 5448dfd465ac
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with linear dependency chain
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
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
        """
        Test diamond pattern: setup -> (build, test) -> deploy runs shared dep once.
        @athena: 95484a33f092
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with diamond dependency
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  setup:
    outputs: [setup.log]
    cmd: echo setup > setup.log

  build:
    deps: [setup]
    outputs: [build.log]
    cmd: echo build > build.log

  test:
    deps: [setup]
    outputs: [test.log]
    cmd: echo test > test.log

  deploy:
    deps: [build, test]
    outputs: [deploy.log]
    cmd: echo deploy > deploy.log
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
        """
        Test modifying dependency input triggers dependent tasks.
        @athena: 3bb6f03ca19d
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input file for gen-config
            config_input = project_root / "config.template"
            config_input.write_text("config template")

            # Create recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
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

    def test_dependency_runs_but_produces_no_changes(self):
        """
        Test that a task whose dependency runs but produces no output changes
        does NOT trigger re-execution.

        Scenario:
        - Task 'build' has no inputs, declares outputs (always runs, like cargo/make)
        - Task 'build' runs but produces no new changes (second run does nothing)
        - Task 'package' depends on 'build' (implicitly gets build outputs as inputs)
        - Expected: 'package' should NOT run because build's outputs didn't change
        - Bug (if present): 'package' runs because 'build' has will_run=True
        @athena: 54669115d3bd
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe file
            recipe = {
                "tasks": {
                    "build": {
                        "desc": "Simulate build tool (cargo/make) with internal dep resolution",
                        "outputs": ["build-artifact.txt"],
                        "cmd": "touch build-artifact.txt",
                    },
                    "package": {
                        "desc": "Package depends on build outputs",
                        "deps": ["build"],
                        "outputs": ["package.tar.gz"],
                        "cmd": "touch package.tar.gz",
                    },
                }
            }

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(yaml.dump(recipe))

            # First run: establish baseline
            # This creates build-artifact.txt and package.tar.gz
            parsed_recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(parsed_recipe, state_manager)

            statuses = executor.execute_task("package")

            assert statuses["build"].will_run  # First run, no state
            assert statuses["package"].will_run  # First run, no state

            # Verify files exist
            assert (project_root / "build-artifact.txt").exists()
            assert (project_root / "package.tar.gz").exists()

            # Record the mtime of build artifact
            build_artifact_path = project_root / "build-artifact.txt"
            original_mtime = build_artifact_path.stat().st_mtime

            # Small delay to ensure time resolution
            time.sleep(0.01)

            # Second run: build task runs (no inputs) but produces no changes
            # Change build command to do nothing (simulates cargo/make finding nothing to do)
            recipe["tasks"]["build"][
                "cmd"
            ] = 'echo "checking dependencies, nothing to do"'
            recipe_path.write_text(yaml.dump(recipe))

            parsed_recipe = parse_recipe(recipe_path)
            executor = Executor(parsed_recipe, state_manager)

            statuses = executor.execute_task("package")

            # Build task should run (changed command = new task definition = "never_run")
            # OR if command hadn't changed, would be "no_outputs" (has outputs but no inputs)
            assert statuses["build"].will_run
            assert statuses["build"].reason in ["no_outputs", "never_run"]

            # Verify build-artifact.txt mtime unchanged
            # (build command didn't touch it)
            current_mtime = build_artifact_path.stat().st_mtime
            assert (
                current_mtime == original_mtime
            ), f"Build artifact mtime changed unexpectedly: {original_mtime} -> {current_mtime}"

            # BUG FIX VERIFICATION: Package task should NOT run
            # because build's implicit output (build-artifact.txt) has unchanged mtime
            # This is the CORE assertion that verifies the bug is fixed
            assert not statuses[
                "package"
            ].will_run, f"Package should not run when dependency produces no changes, but will_run={statuses['package'].will_run}, reason={statuses['package'].reason}"

            assert (
                statuses["package"].reason == "fresh"
            ), f"Package should be fresh, but reason={statuses['package'].reason}"

    def test_dependency_actually_changes_outputs(self):
        """
        Test that tasks DO run when dependency outputs actually change.

        This is the positive test case - ensure we didn't break normal behavior.
        @athena: 47401bca0465
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe
            recipe = {
                "tasks": {
                    "generate": {
                        "desc": "Generate a file",
                        "outputs": ["config.json"],
                        "cmd": "echo '{}' > config.json",
                    },
                    "build": {
                        "desc": "Build using generated file",
                        "deps": ["generate"],
                        "outputs": ["app"],
                        "cmd": "touch app",
                    },
                }
            }

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(yaml.dump(recipe))

            # First run: establish baseline
            parsed_recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(parsed_recipe, state_manager)

            statuses = executor.execute_task("build")

            assert statuses["generate"].will_run
            assert statuses["build"].will_run

            # Small delay
            time.sleep(0.01)

            # Second run: modify generate command so it changes its output
            recipe["tasks"]["generate"]["cmd"] = "echo '{\"version\": 2}' > config.json"
            recipe_path.write_text(yaml.dump(recipe))

            parsed_recipe = parse_recipe(recipe_path)
            executor = Executor(parsed_recipe, state_manager)

            statuses = executor.execute_task("build")

            # Generate runs (changed command = new definition = "never_run")
            # OR if command hadn't changed, would be "no_outputs" (has outputs but no inputs)
            assert statuses["generate"].will_run
            assert statuses["generate"].reason in ["no_outputs", "never_run"]

            # Build SHOULD run because generate's output changed
            assert statuses[
                "build"
            ].will_run, "Build should run when dependency output changes"
            # Reason could be "inputs_changed" or "never_run" (if generate's definition change
            # cascades to make build's implicit inputs appear as first-time)
            assert statuses["build"].reason in [
                "inputs_changed",
                "never_run",
            ], f"Build should run, got reason={statuses['build'].reason}"


if __name__ == "__main__":
    unittest.main()
