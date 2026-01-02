"""Integration tests for CLI options vs user task names."""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


class TestCLIOptionsNoClash(unittest.TestCase):
    """Test that CLI options (--show, --tree, etc.) don't clash with user task names."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}  # Disable color output for consistent assertions

    def test_user_tasks_with_builtin_names(self):
        """Test that user can create tasks named 'show', 'tree', 'init', etc.

        This verifies that built-in options (--show, --tree, --init) don't prevent
        users from creating tasks with those names.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml with tasks named after built-in options
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  show:
    desc: User task named 'show'
    cmd: echo "Running user's show task"

  tree:
    desc: User task named 'tree'
    cmd: echo "Running user's tree task"

  init:
    desc: User task named 'init'
    cmd: echo "Running user's init task"

  list:
    desc: User task named 'list'
    cmd: echo "Running user's list task"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test 1: User tasks can be executed
                result = self.runner.invoke(app, ["show"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'show' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["tree"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'tree' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["init"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'init' completed successfully", result.stdout)

                result = self.runner.invoke(app, ["list"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("Task 'list' completed successfully", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_builtin_options_still_work(self):
        """Test that built-in options still work when user has tasks with same names."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a tasktree.yaml with tasks named after built-in options
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  show:
    desc: User task named 'show'
    cmd: echo "Running user's show task"

  build:
    desc: Build task
    outputs: [output.txt]
    cmd: echo "building" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test that --show (built-in option) still works
                result = self.runner.invoke(app, ["--show", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build:", result.stdout)
                self.assertIn("desc: Build task", result.stdout)
                # Should NOT execute the user's "show" task
                self.assertNotIn("Running user's show task", result.stdout)

                # Test that --list (built-in option) still works
                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                # New borderless format shows task names without a title
                self.assertIn("show", result.stdout)
                self.assertIn("build", result.stdout)

                # Test that --tree (built-in option) still works
                result = self.runner.invoke(app, ["--tree", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build", result.stdout)
                # Should NOT execute the user's "show" task
                self.assertNotIn("Running user's show task", result.stdout)
            finally:
                os.chdir(original_cwd)

            # Test that --init creates a new file (in a subdir to not conflict)
            init_dir = project_root / "subdir"
            init_dir.mkdir()
            original_cwd = os.getcwd()
            try:
                os.chdir(init_dir)
                result = self.runner.invoke(app, ["--init"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((init_dir / "tasktree.yaml").exists())
                self.assertIn("Created", result.stdout)
            finally:
                os.chdir(original_cwd)

    def test_double_dash_required_for_options(self):
        """Test that single-word options don't work - must use double-dash."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    desc: Build task
    cmd: echo "building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Single word "show" should be treated as a task name (and fail)
                result = self.runner.invoke(app, ["show", "build"], env=self.env)
                # This should fail because "show" task doesn't exist
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("Task not found: show", result.stdout)

                # But --show should work
                result = self.runner.invoke(app, ["--show", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertIn("build:", result.stdout)
            finally:
                os.chdir(original_cwd)


    def test_help_option_works(self):
        """Test that --help and -h options work correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a simple recipe
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    desc: Build task
    cmd: echo "building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Test --help
                result = self.runner.invoke(app, ["--help"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Strip ANSI codes for reliable assertions
                output = strip_ansi_codes(result.stdout)

                self.assertIn("Task Tree", output)
                self.assertIn("Usage:", output)
                # Typer formats it with a box, so just check for "Options"
                self.assertIn("Options", output)
                self.assertIn("--help", output)
                self.assertIn("--version", output)
                self.assertIn("--list", output)
                self.assertIn("--show", output)
                self.assertIn("--tree", output)
                self.assertIn("--init", output)
                self.assertIn("--clean", output)
            finally:
                os.chdir(original_cwd)


class TestShowOption(unittest.TestCase):
    """Test the --show option displays task definitions correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_show_multiline_command_preserves_newlines(self):
        """Test that --show displays multiline commands with proper newlines, not escaped \\n."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("tasktree.yaml")
            recipe_file.write_text(
                """
tasks:
  multiline:
    desc: Task with multiline command
    cmd: |
      echo "Line 1"
      echo "Line 2"
      echo "Line 3"
"""
            )

            result = self.runner.invoke(app, ["--show", "multiline"], env=self.env)

            self.assertEqual(result.exit_code, 0)

            # Should show the literal block style indicator
            self.assertIn("cmd: |", result.stdout)

            # Should show each line on a separate line (not escaped \\n)
            self.assertIn('echo "Line 1"', result.stdout)
            self.assertIn('echo "Line 2"', result.stdout)
            self.assertIn('echo "Line 3"', result.stdout)

            # Should NOT show escaped newlines
            self.assertNotIn("\\n", result.stdout)

    def test_show_single_line_command(self):
        """Test that --show displays single-line commands cleanly."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("tasktree.yaml")
            recipe_file.write_text(
                """
tasks:
  single:
    desc: Task with single line command
    cmd: echo "Hello world"
"""
            )

            result = self.runner.invoke(app, ["--show", "single"], env=self.env)

            self.assertEqual(result.exit_code, 0)

            # Should show the command on a single line
            self.assertIn('cmd: echo "Hello world"', result.stdout)

            # Should NOT use literal block style for single-line commands
            self.assertNotIn("cmd: |", result.stdout)


class TestForceOption(unittest.TestCase):
    """Test the --force/-f option forces re-run of all tasks."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_force_option_reruns_fresh_tasks(self):
        """Test --force causes fresh tasks to re-run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input and recipe
            input_file = project_root / "input.txt"
            input_file.write_text("initial")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    inputs: [input.txt]
    outputs: [output.txt]
    cmd: cat input.txt > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - task executes
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                self.assertTrue((project_root / "output.txt").exists())
                output_time_1 = (project_root / "output.txt").stat().st_mtime

                # Second run - task skips (fresh)
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.txt").stat().st_mtime
                self.assertEqual(output_time_1, output_time_2)  # Not modified

                # Third run with --force - task executes even though fresh
                import time
                time.sleep(0.01)  # Ensure mtime can change
                result = self.runner.invoke(app, ["--force", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_3 = (project_root / "output.txt").stat().st_mtime
                self.assertGreater(output_time_3, output_time_2)  # Was modified

            finally:
                os.chdir(original_cwd)

    def test_force_short_flag_works(self):
        """Test -f short flag works as alias for --force."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [output.txt]
    cmd: echo "built" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run once
                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_1 = (project_root / "output.txt").stat().st_mtime

                # Run with -f (short flag)
                import time
                time.sleep(0.01)
                result = self.runner.invoke(app, ["-f", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                output_time_2 = (project_root / "output.txt").stat().st_mtime
                self.assertGreater(output_time_2, output_time_1)

            finally:
                os.chdir(original_cwd)

    def test_force_reruns_dependencies(self):
        """Test --force re-runs all dependencies in chain."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  lint:
    outputs: [lint.log]
    cmd: echo "linting" > lint.log

  build:
    deps: [lint]
    outputs: [build.log]
    cmd: echo "building" > build.log

  test:
    deps: [build]
    outputs: [test.log]
    cmd: echo "testing" > test.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - all execute
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                lint_time_1 = (project_root / "lint.log").stat().st_mtime
                build_time_1 = (project_root / "build.log").stat().st_mtime
                test_time_1 = (project_root / "test.log").stat().st_mtime

                # Second run - all skip (fresh)
                result = self.runner.invoke(app, ["test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                lint_time_2 = (project_root / "lint.log").stat().st_mtime
                build_time_2 = (project_root / "build.log").stat().st_mtime
                test_time_2 = (project_root / "test.log").stat().st_mtime
                self.assertEqual(lint_time_1, lint_time_2)
                self.assertEqual(build_time_1, build_time_2)
                self.assertEqual(test_time_1, test_time_2)

                # Third run with --force - all re-execute
                import time
                time.sleep(0.01)
                result = self.runner.invoke(app, ["--force", "test"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                lint_time_3 = (project_root / "lint.log").stat().st_mtime
                build_time_3 = (project_root / "build.log").stat().st_mtime
                test_time_3 = (project_root / "test.log").stat().st_mtime
                self.assertGreater(lint_time_3, lint_time_2)
                self.assertGreater(build_time_3, build_time_2)
                self.assertGreater(test_time_3, test_time_2)

            finally:
                os.chdir(original_cwd)


class TestOnlyOption(unittest.TestCase):
    """Test the --only/-o option that skips dependencies."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_only_option_skips_dependencies(self):
        """Test --only executes only the target task, not dependencies."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  lint:
    outputs: [lint.log]
    cmd: echo "linting" > lint.log

  build:
    deps: [lint]
    outputs: [build.log]
    cmd: echo "building" > build.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run build with --only
                result = self.runner.invoke(app, ["--only", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify build ran
                self.assertTrue((project_root / "build.log").exists())

                # Verify lint did NOT run
                self.assertFalse((project_root / "lint.log").exists())

            finally:
                os.chdir(original_cwd)

    def test_only_short_flag_works(self):
        """Test -o short flag works as alias for --only."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  lint:
    outputs: [lint.log]
    cmd: echo "linting" > lint.log

  build:
    deps: [lint]
    outputs: [build.log]
    cmd: echo "building" > build.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run build with -o
                result = self.runner.invoke(app, ["-o", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify build ran
                self.assertTrue((project_root / "build.log").exists())

                # Verify lint did NOT run
                self.assertFalse((project_root / "lint.log").exists())

            finally:
                os.chdir(original_cwd)

    def test_only_option_with_dependency_chain(self):
        """Test --only skips entire dependency chain."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  lint:
    outputs: [lint.log]
    cmd: echo "linting" > lint.log

  build:
    deps: [lint]
    outputs: [build.log]
    cmd: echo "building" > build.log

  test:
    deps: [build]
    outputs: [test.log]
    cmd: echo "testing" > test.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run test with --only
                result = self.runner.invoke(app, ["--only", "test"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify only test ran
                self.assertTrue((project_root / "test.log").exists())
                self.assertFalse((project_root / "build.log").exists())
                self.assertFalse((project_root / "lint.log").exists())

            finally:
                os.chdir(original_cwd)

    def test_only_option_forces_execution(self):
        """Test --only forces execution (ignores freshness)."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  build:
    outputs: [build.log]
    cmd: echo "building" > build.log
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run
                result = self.runner.invoke(app, ["--only", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                build_time_1 = (project_root / "build.log").stat().st_mtime

                # Second run (should re-run because --only implies --force)
                import time
                time.sleep(0.01)
                result = self.runner.invoke(app, ["--only", "build"], env=self.env)
                self.assertEqual(result.exit_code, 0)
                build_time_2 = (project_root / "build.log").stat().st_mtime

                # Verify build was re-run
                self.assertGreater(build_time_2, build_time_1)

            finally:
                os.chdir(original_cwd)


class TestListOptionWithImports(unittest.TestCase):
    """Test that --list option shows imported tasks."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_list_shows_imported_tasks(self):
        """Test that imported tasks are shown in --list output with namespaced names."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create base.yaml with some tasks
            (project_root / "base.yaml").write_text("""
tasks:
  setup:
    desc: Setup base infrastructure
    cmd: echo "Setting up base"

  configure:
    desc: Configure base settings
    cmd: echo "Configuring base"
""")

            # Create common.yaml that imports base.yaml
            (project_root / "common.yaml").write_text("""
imports:
  - file: base.yaml
    as: base

tasks:
  prepare:
    desc: Prepare common resources
    deps: [base.setup]
    cmd: echo "Preparing common"
""")

            # Create main recipe that imports common.yaml
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: common.yaml
    as: common

tasks:
  build:
    desc: Build the project
    deps: [common.prepare]
    cmd: echo "Building project"

  test:
    desc: Run tests
    deps: [build]
    cmd: echo "Running tests"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run --list
                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Strip ANSI codes for reliable assertions
                output = strip_ansi_codes(result.stdout)

                # Verify main tasks are listed
                self.assertIn("build", output)
                self.assertIn("test", output)

                # Verify imported tasks are listed with namespace
                self.assertIn("common.prepare", output)
                self.assertIn("common.base.setup", output)
                self.assertIn("common.base.configure", output)

                # Verify descriptions are shown
                self.assertIn("Build the project", output)
                self.assertIn("Run tests", output)
                self.assertIn("Prepare common resources", output)
                self.assertIn("Setup base infrastructure", output)
                self.assertIn("Configure base settings", output)

            finally:
                os.chdir(original_cwd)

    def test_list_shows_single_level_import(self):
        """Test that --list shows tasks from a single-level import."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create imported file
            (project_root / "shared.yaml").write_text("""
tasks:
  lint:
    desc: Run linter
    cmd: echo "Linting code"

  format:
    desc: Format code
    cmd: echo "Formatting code"
""")

            # Create main recipe
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
imports:
  - file: shared.yaml
    as: shared

tasks:
  build:
    desc: Build application
    cmd: echo "Building"
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run --list
                result = self.runner.invoke(app, ["--list"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                output = strip_ansi_codes(result.stdout)

                # Verify all tasks are listed
                self.assertIn("build", output)
                self.assertIn("shared.lint", output)
                self.assertIn("shared.format", output)

                # Verify descriptions
                self.assertIn("Build application", output)
                self.assertIn("Run linter", output)
                self.assertIn("Format code", output)

            finally:
                os.chdir(original_cwd)


class TestTasksFileOption(unittest.TestCase):
    """Test the --tasks/-T option for specifying recipe files."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_tasks_option_with_yml_extension(self):
        """Test --tasks option works with .yml extension."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("tasktree.yml")
            recipe_file.write_text(
                """
tasks:
  build:
    desc: Build with yml
    cmd: echo "Building from yml"
"""
            )

            result = self.runner.invoke(app, ["--tasks", "tasktree.yml", "build"], env=self.env)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("build", result.stdout)
            self.assertIn("completed successfully", result.stdout)

    def test_tasks_option_with_tasks_extension(self):
        """Test --tasks option works with .tasks extension."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("build.tasks")
            recipe_file.write_text(
                """
tasks:
  compile:
    desc: Compile code
    cmd: echo "Compiling"
"""
            )

            result = self.runner.invoke(app, ["--tasks", "build.tasks", "compile"], env=self.env)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("compile", result.stdout)
            self.assertIn("completed successfully", result.stdout)

    def test_tasks_option_with_short_flag(self):
        """Test -T short flag works."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("my.tasks")
            recipe_file.write_text(
                """
tasks:
  test:
    cmd: echo "Testing"
"""
            )

            result = self.runner.invoke(app, ["-T", "my.tasks", "test"], env=self.env)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("test", result.stdout)
            self.assertIn("completed successfully", result.stdout)

    def test_multiple_recipe_files_without_tasks_option_fails(self):
        """Test that having multiple recipe files without --tasks raises error."""
        with self.runner.isolated_filesystem():
            # Create multiple recipe files
            Path("tasktree.yaml").write_text("tasks:\n  build:\n    cmd: echo yaml")
            Path("tasktree.yml").write_text("tasks:\n  build:\n    cmd: echo yml")

            # Should fail with helpful error message
            result = self.runner.invoke(app, ["build"], env=self.env)

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Multiple recipe files found", result.stdout)
            self.assertIn("--tasks", result.stdout)

    def test_tasks_option_selects_specific_file_when_multiple_exist(self):
        """Test --tasks option selects specific file when multiple exist."""
        with self.runner.isolated_filesystem():
            # Create multiple recipe files with different task names
            Path("tasktree.yaml").write_text(
                """
tasks:
  yaml-task:
    cmd: echo "From yaml"
"""
            )
            Path("build.tasks").write_text(
                """
tasks:
  tasks-task:
    cmd: echo "From tasks"
"""
            )

            # Use --tasks to select the .tasks file - should be able to run tasks-task
            result = self.runner.invoke(app, ["--tasks", "build.tasks", "tasks-task"], env=self.env)
            self.assertEqual(result.exit_code, 0)
            self.assertIn("tasks-task", result.stdout)

            # Should not be able to run yaml-task from build.tasks
            result = self.runner.invoke(app, ["--tasks", "build.tasks", "yaml-task"], env=self.env)
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Task not found", result.stdout)

    def test_tasks_option_with_list(self):
        """Test --tasks option works with --list."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("custom.tasks")
            recipe_file.write_text(
                """
tasks:
  task1:
    desc: First task
    cmd: echo one
  task2:
    desc: Second task
    cmd: echo two
"""
            )

            result = self.runner.invoke(app, ["--tasks", "custom.tasks", "--list"], env=self.env)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("task1", result.stdout)
            self.assertIn("task2", result.stdout)
            self.assertIn("First task", result.stdout)

    def test_tasks_option_with_show(self):
        """Test --tasks option works with --show."""
        with self.runner.isolated_filesystem():
            recipe_file = Path("my.tasks")
            recipe_file.write_text(
                """
tasks:
  build:
    desc: Build task
    cmd: echo building
"""
            )

            result = self.runner.invoke(app, ["--tasks", "my.tasks", "--show", "build"], env=self.env)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("build:", result.stdout)
            self.assertIn("desc: Build task", result.stdout)

    def test_tasks_option_with_nonexistent_file(self):
        """Test --tasks option with nonexistent file shows error."""
        with self.runner.isolated_filesystem():
            result = self.runner.invoke(app, ["--tasks", "nonexistent.yaml", "build"], env=self.env)

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Recipe file not found", result.stdout)
            self.assertIn("nonexistent.yaml", result.stdout)


if __name__ == "__main__":
    unittest.main()
