"""Tests for executor module."""

import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from tasktree.executor import Executor, TaskStatus
from tasktree.parser import Recipe, Task
from tasktree.state import StateManager, TaskState


class TestTaskStatus(unittest.TestCase):
    def test_check_never_run(self):
        """Test status for task that has never run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="cargo build", outputs=["target/bin"])}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(tasks["build"], {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "never_run")

    def test_check_no_outputs(self):
        """Test status for task with no inputs and no outputs (always runs)."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="cargo test")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(tasks["test"], {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "no_outputs")

    def test_check_fresh(self):
        """Test status for task that is fresh."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input file
            input_file = project_root / "input.txt"
            input_file.write_text("hello")

            # Create output file (task has run successfully before)
            output_file = project_root / "output.txt"
            output_file.write_text("output")

            # Create state with old mtime
            state_manager = StateManager(project_root)
            from tasktree.hasher import hash_task, make_cache_key

            task = Task(name="build", cmd="cat input.txt", inputs=["input.txt"], outputs=["output.txt"])
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args)
            cache_key = make_cache_key(task_hash)

            # Set state with current mtime
            current_mtime = input_file.stat().st_mtime
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={"input.txt": current_mtime}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")


class TestExecutor(unittest.TestCase):
    @patch("subprocess.run")
    def test_execute_simple_task(self, mock_run):
        """Test executing a simple task."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="cargo build")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify subprocess was called
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            self.assertEqual(call_args[0][0], "cargo build")
            self.assertTrue(call_args[1]["shell"])

    @patch("subprocess.run")
    def test_execute_with_dependencies(self, mock_run):
        """Test executing task with dependencies."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="cargo clippy"),
                "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            }
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify both tasks were executed
            self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    def test_execute_with_args(self, mock_run):
        """Test executing task with arguments."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "deploy": Task(
                    name="deploy",
                    cmd="echo Deploying to {{environment}}",
                    args=["environment"],
                )
            }
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("deploy", {"environment": "production"})

            # Verify command had arguments substituted
            call_args = mock_run.call_args
            self.assertEqual(call_args[0][0], "echo Deploying to production")


class TestMissingOutputs(unittest.TestCase):
    def test_fresh_task_with_all_outputs_present(self):
        """Test that fresh task with all outputs present should skip."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create output file
            output_file = project_root / "output.txt"
            output_file.write_text("output")

            # Create state
            state_manager = StateManager(project_root)
            from tasktree.hasher import hash_task, make_cache_key

            task = Task(
                name="build",
                cmd="echo test > output.txt",
                outputs=["output.txt"],
            )
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args)
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")

    def test_fresh_task_with_missing_output(self):
        """Test that fresh task with missing output should run with outputs_missing reason."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Do NOT create output file - it's missing

            # Create state (task ran before)
            state_manager = StateManager(project_root)
            from tasktree.hasher import hash_task, make_cache_key

            task = Task(
                name="build",
                cmd="echo test > output.txt",
                outputs=["output.txt"],
            )
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args)
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")
            self.assertEqual(status.changed_files, ["output.txt"])

    def test_fresh_task_with_partial_outputs(self):
        """Test that task with some outputs present but not all should run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create only one of two outputs
            output1 = project_root / "output1.txt"
            output1.write_text("output1")
            # output2.txt is missing

            state_manager = StateManager(project_root)
            from tasktree.hasher import hash_task, make_cache_key

            task = Task(
                name="build",
                cmd="echo test",
                outputs=["output1.txt", "output2.txt"],
            )
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args)
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")
            self.assertIn("output2.txt", status.changed_files)

    def test_task_with_no_state_should_not_warn_about_outputs(self):
        """Test that first run (no state) uses never_run reason, not outputs_missing."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            task = Task(
                name="build",
                cmd="echo test > output.txt",
                outputs=["output.txt"],
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "never_run")  # Not outputs_missing

    def test_task_with_no_outputs_unaffected(self):
        """Test that tasks with no outputs declared are unaffected."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            task = Task(name="test", cmd="echo test")  # No outputs

            tasks = {"test": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "no_outputs")  # Always runs

    def test_output_glob_pattern_with_working_dir(self):
        """Test that output patterns resolve correctly with working_dir."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create subdirectory
            subdir = project_root / "subdir"
            subdir.mkdir()

            # Create output in subdirectory
            output_file = subdir / "output.txt"
            output_file.write_text("output")

            state_manager = StateManager(project_root)
            from tasktree.hasher import hash_task, make_cache_key

            task = Task(
                name="build",
                cmd="echo test > output.txt",
                working_dir="subdir",
                outputs=["output.txt"],
            )
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args)
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")

    def test_output_glob_pattern_no_matches(self):
        """Test that glob pattern with zero matches triggers re-run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create dist directory but no .deb files
            dist_dir = project_root / "dist"
            dist_dir.mkdir()

            state_manager = StateManager(project_root)
            from tasktree.hasher import hash_task, make_cache_key

            task = Task(
                name="package",
                cmd="create-deb",
                outputs=["dist/*.deb"],
            )
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args)
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"package": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")


class TestExecutorErrors(unittest.TestCase):
    """Tests for executor error conditions."""

    def test_execute_subprocess_failure(self):
        """Test ExecutionError raised when subprocess fails."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
fail:
  cmd: exit 1
"""
            )

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager)

            with self.assertRaises(ExecutionError) as cm:
                executor.execute_task("fail", {})
            self.assertIn("exit code", str(cm.exception).lower())

    def test_execute_working_dir_not_found(self):
        """Test error when working directory doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
test:
  working_dir: nonexistent_directory
  cmd: echo "test"
"""
            )

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager)

            with self.assertRaises((ExecutionError, FileNotFoundError, OSError)):
                executor.execute_task("test", {})

    def test_execute_command_not_found(self):
        """Test error when command doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
test:
  cmd: nonexistent_command_12345
"""
            )

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager)

            with self.assertRaises(ExecutionError):
                executor.execute_task("test", {})

    def test_execute_permission_denied(self):
        """Test error when command not executable."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a script file without execute permissions
            script_path = project_root / "script.sh"
            script_path.write_text("#!/bin/bash\necho test")
            script_path.chmod(0o644)  # Read/write but not execute

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                f"""
test:
  cmd: {script_path}
"""
            )

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager)

            with self.assertRaises((ExecutionError, PermissionError, OSError)):
                executor.execute_task("test", {})


class TestExecutorPrivateMethods(unittest.TestCase):
    """Tests for executor private methods."""

    def test_substitute_args_single(self):
        """Test substituting single argument."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="echo {{environment}}")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            result = executor._substitute_args("echo {{environment}}", {"environment": "production"})
            self.assertEqual(result, "echo production")

    def test_substitute_args_multiple(self):
        """Test substituting multiple arguments."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="deploy {{app}} to {{region}}")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            result = executor._substitute_args(
                "deploy {{app}} to {{region}}",
                {"app": "myapp", "region": "us-east-1"}
            )
            self.assertEqual(result, "deploy myapp to us-east-1")

    def test_substitute_args_missing_placeholder(self):
        """Test leaves unreplaced placeholders when arg not provided."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="echo {{environment}} {{missing}}")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            result = executor._substitute_args(
                "echo {{environment}} {{missing}}",
                {"environment": "production"}
            )
            # Missing placeholder should remain
            self.assertEqual(result, "echo production {{missing}}")

    def test_check_inputs_changed_mtime(self):
        """Test detects changed file by mtime."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create input file
            input_file = project_root / "input.txt"
            input_file.write_text("original")
            original_mtime = input_file.stat().st_mtime

            # Create state with old mtime
            state_manager = StateManager(project_root)
            task = Task(name="build", cmd="cat input.txt", inputs=["input.txt"])

            # Create cached state with original mtime
            cached_state = TaskState(
                last_run=time.time(),
                input_state={"input.txt": original_mtime - 100}  # Older mtime
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            # Check if inputs changed
            changed = executor._check_inputs_changed(task, cached_state, ["input.txt"])

            # Should detect change because current mtime > cached mtime
            self.assertEqual(changed, ["input.txt"])

    def test_check_outputs_missing(self):
        """Test detects missing output files."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Task declares outputs but files don't exist
            task = Task(
                name="build",
                cmd="echo test > output.txt",
                outputs=["output.txt"]
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            # Check for missing outputs
            missing = executor._check_outputs_missing(task)

            # Should detect output.txt is missing
            self.assertEqual(missing, ["output.txt"])

    def test_expand_globs_multiple_patterns(self):
        """Test expanding multiple glob patterns."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test files
            (project_root / "file1.txt").write_text("test1")
            (project_root / "file2.txt").write_text("test2")
            (project_root / "script.py").write_text("print('test')")

            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo test")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            # Expand multiple patterns
            result = executor._expand_globs(["*.txt", "*.py"], ".")

            # Should find all matching files
            self.assertEqual(set(result), {"file1.txt", "file2.txt", "script.py"})


if __name__ == "__main__":
    unittest.main()
