"""Tests for executor module."""

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from tasktree.executor import Executor, TaskStatus
from tasktree.parser import Recipe, Task
from tasktree.state import StateManager, TaskState


class TestTaskStatus(unittest.TestCase):
    """
    @athena: 3042cefdbba4
    """
    def test_check_never_run(self):
        """
        Test status for task that has never run.
        @athena: 442a5215f152
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="cargo build", outputs=["target/bin"])}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(tasks["build"], {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "never_run")

    def test_check_no_outputs(self):
        """
        Test status for task with no inputs and no outputs (always runs).
        @athena: 61274fd5e6fd
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="cargo test")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(tasks["test"], {}, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "no_outputs")

    def test_check_fresh(self):
        """
        Test status for task that is fresh.
        @athena: e02f287e5128
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            # Set state with current mtime
            current_mtime = input_file.stat().st_mtime
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={"input.txt": current_mtime}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")


class TestExecutor(unittest.TestCase):
    """
    @athena: 757a0e3e8359
    """
    @patch("subprocess.run")
    @patch("os.chmod")
    def test_execute_simple_task(self, mock_chmod, mock_run):
        """
        Test executing a simple task.
        @athena: 6317905c844f
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="cargo build")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify subprocess was called with a script path
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            # Command should be passed as [script_path]
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

    @patch("subprocess.run")
    def test_execute_with_dependencies(self, mock_run):
        """
        Test executing task with dependencies.
        @athena: 1deabb08cdfa
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="cargo clippy"),
                "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            }
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify both tasks were executed
            self.assertEqual(mock_run.call_count, 2)

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_execute_with_args(self, mock_chmod, mock_run):
        """
        Test executing task with arguments.
        @athena: 73be40a7105b
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "deploy": Task(
                    name="deploy",
                    cmd="echo Deploying to {{ arg.environment }}",
                    args=["environment"],
                )
            }
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("deploy", {"environment": "production"})

            # Verify command had arguments substituted and passed as script
            call_args = mock_run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

    @patch("subprocess.run")
    @patch("os.chmod")
    @patch("os.unlink")
    def test_run_command_as_script_single_line(self, mock_unlink, mock_chmod, mock_run):
        """
        Test _run_command_as_script with single-line command.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Call the unified method directly
            executor._run_command_as_script(
                cmd="echo hello",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble=""
            )

            # Verify subprocess.run was called with a script path
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh"))

            # Verify chmod was called to make script executable
            mock_chmod.assert_called_once()

            # Verify cleanup (unlink) was called
            mock_unlink.assert_called_once()

    @patch("subprocess.run")
    @patch("os.chmod")
    @patch("os.unlink")
    def test_run_command_as_script_with_preamble(self, mock_unlink, mock_chmod, mock_run):
        """
        Test _run_command_as_script with preamble.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Call with preamble
            executor._run_command_as_script(
                cmd="echo hello",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble="set -e\n"
            )

            # Verify subprocess.run was called
            mock_run.assert_called_once()

            # Verify chmod was called
            mock_chmod.assert_called_once()

            # Verify cleanup
            mock_unlink.assert_called_once()

    @patch("subprocess.run")
    @patch("os.chmod")
    @patch("os.unlink")
    def test_run_command_as_script_multiline(self, mock_unlink, mock_chmod, mock_run):
        """
        Test _run_command_as_script with multi-line command.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello\necho world")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Call with multi-line command
            executor._run_command_as_script(
                cmd="echo hello\necho world",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble=""
            )

            # Verify subprocess.run was called
            mock_run.assert_called_once()

            # Verify chmod was called
            mock_chmod.assert_called_once()

            # Verify cleanup
            mock_unlink.assert_called_once()


class TestMissingOutputs(unittest.TestCase):
    """
    @athena: 94dc69acf126
    """
    def test_fresh_task_with_all_outputs_present(self):
        """
        Test that fresh task with all outputs present should skip.
        @athena: 401d95b3c44f
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")

    def test_fresh_task_with_missing_output(self):
        """
        Test that fresh task with missing output should run with outputs_missing reason.
        @athena: 3ef83cd3acb8
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")
            self.assertEqual(status.changed_files, ["output.txt"])

    def test_fresh_task_with_partial_outputs(self):
        """
        Test that task with some outputs present but not all should run.
        @athena: 6217f859b234
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")
            self.assertIn("output2.txt", status.changed_files)

    def test_task_with_no_state_should_not_warn_about_outputs(self):
        """
        Test that first run (no state) uses never_run reason, not outputs_missing.
        @athena: 5c8a63d5d9db
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            task = Task(
                name="build",
                cmd="echo test > output.txt",
                outputs=["output.txt"],
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "never_run")  # Not outputs_missing

    def test_task_with_no_outputs_unaffected(self):
        """
        Test that tasks with no outputs declared are unaffected.
        @athena: 782e6a7191c1
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            task = Task(name="test", cmd="echo test")  # No outputs

            tasks = {"test": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "no_outputs")  # Always runs

    def test_output_glob_pattern_with_working_dir(self):
        """
        Test that output patterns resolve correctly with working_dir.
        @athena: 9c15753c5915
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")

    def test_output_glob_pattern_no_matches(self):
        """
        Test that glob pattern with zero matches triggers re-run.
        @athena: e01cba21a778
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"package": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            status = executor.check_task_status(task, {})
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")


class TestExecutorErrors(unittest.TestCase):
    """
    Tests for executor error conditions.
    @athena: b2f15c55b066
    """

    def test_execute_subprocess_failure(self):
        """
        Test ExecutionError raised when subprocess fails.
        @athena: ba9aa0ed5f95
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
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
        """
        Test error when working directory doesn't exist.
        @athena: f38eafecd3a0
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
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
        """
        Test error when command doesn't exist.
        @athena: c07df55f1b3f
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
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
        """
        Test error when command not executable.
        @athena: bd873c327af3
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a script file without execute permissions
            script_path = project_root / "script.sh"
            script_path.write_text("#!/bin/bash\necho test")
            script_path.chmod(0o644)  # Read/write but not execute

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                f"""
tasks:
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

    def test_builtin_working_dir_in_working_dir_raises_error(self):
        """
        Test that using {{ tt.working_dir }} in working_dir raises clear error.
        @athena: 8ef45062b0a7
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  test:
    working_dir: "{{ tt.working_dir }}/subdir"
    cmd: echo "test"
"""
            )

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager)

            with self.assertRaises(ExecutionError) as cm:
                executor.execute_task("test", {})

            error_msg = str(cm.exception)
            self.assertIn("Cannot use {{ tt.working_dir }}", error_msg)
            self.assertIn("circular dependency", error_msg)

    def test_other_builtin_vars_in_working_dir_allowed(self):
        """
        Test that non-circular builtin vars like {{ tt.task_name }} work in working_dir.
        @athena: fef78b324ff7
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory using task name
            task_subdir = project_root / "test-task"
            task_subdir.mkdir()

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(
                """
tasks:
  test-task:
    working_dir: "{{ tt.task_name }}"
    cmd: pwd
"""
            )

            from tasktree.executor import Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager)

            # Should not raise - tt.task_name is allowed in working_dir
            executor.execute_task("test-task", {})


class TestExecutorPrivateMethods(unittest.TestCase):
    """
    Tests for executor private methods.
    @athena: eb2d4e3a6176
    """

    def test_substitute_args_single(self):
        """
        Test substituting single argument.
        @athena: af49a9f9df9c
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="echo {{ arg.environment }}")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            result = executor._substitute_args("echo {{ arg.environment }}", {"environment": "production"})
            self.assertEqual(result, "echo production")

    def test_substitute_args_multiple(self):
        """
        Test substituting multiple arguments.
        @athena: 82c86230f01b
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="deploy {{ arg.app }} to {{ arg.region }}")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            result = executor._substitute_args(
                "deploy {{ arg.app }} to {{ arg.region }}",
                {"app": "myapp", "region": "us-east-1"}
            )
            self.assertEqual(result, "deploy myapp to us-east-1")

    def test_substitute_args_missing_placeholder(self):
        """
        Test raises error when arg not provided.
        @athena: 5cfbd5e8b848
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="echo {{ arg.environment }} {{ arg.missing }}")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            # Missing argument should raise ValueError
            with self.assertRaises(ValueError) as cm:
                executor._substitute_args(
                    "echo {{ arg.environment }} {{ arg.missing }}",
                    {"environment": "production"}
                )
            self.assertIn("missing", str(cm.exception))
            self.assertIn("not defined", str(cm.exception))

    def test_check_inputs_changed_mtime(self):
        """
        Test detects changed file by mtime.
        @athena: d4a66a0298ad
        """
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
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            # Check if inputs changed
            changed = executor._check_inputs_changed(task, cached_state, ["input.txt"])

            # Should detect change because current mtime > cached mtime
            self.assertEqual(changed, ["input.txt"])

    def test_check_outputs_missing(self):
        """
        Test detects missing output files.
        @athena: 993525e7038a
        """
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
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            # Check for missing outputs
            missing = executor._check_outputs_missing(task)

            # Should detect output.txt is missing
            self.assertEqual(missing, ["output.txt"])

    def test_expand_globs_multiple_patterns(self):
        """
        Test expanding multiple glob patterns.
        @athena: 9b42d786c35a
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test files
            (project_root / "file1.txt").write_text("test1")
            (project_root / "file2.txt").write_text("test2")
            (project_root / "script.py").write_text("print('test')")

            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo test")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            # Expand multiple patterns
            result = executor._expand_globs(["*.txt", "*.py"], ".")

            # Should find all matching files
            self.assertEqual(set(result), {"file1.txt", "file2.txt", "script.py"})


class TestOnlyMode(unittest.TestCase):
    """
    Test the --only mode that skips dependencies.
    @athena: 0aa49c9ecf67
    """

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_only_mode_skips_dependencies(self, mock_chmod, mock_run):
        """
        Test that only=True executes only the target task, not dependencies.
        @athena: c6f1351d6ce1
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="echo linting"),
                "build": Task(name="build", cmd="echo building", deps=["lint"]),
            }
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Execute with only=True
            statuses = executor.execute_task("build", only=True)

            # Verify only build was executed, not lint
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

            # Verify statuses only contains the target task
            self.assertEqual(len(statuses), 1)
            self.assertIn("build", statuses)
            self.assertNotIn("lint", statuses)

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_only_mode_with_multiple_dependencies(self, mock_chmod, mock_run):
        """
        Test that only=True skips all dependencies in a chain.
        @athena: 26e51dc2998b
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="echo linting"),
                "build": Task(name="build", cmd="echo building", deps=["lint"]),
                "test": Task(name="test", cmd="echo testing", deps=["build"]),
            }
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Execute test with only=True
            statuses = executor.execute_task("test", only=True)

            # Verify only test was executed
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

            # Verify statuses only contains test
            self.assertEqual(len(statuses), 1)
            self.assertIn("test", statuses)
            self.assertNotIn("build", statuses)
            self.assertNotIn("lint", statuses)

    @patch("subprocess.run")
    def test_only_mode_forces_execution(self, mock_run):
        """
        Test that only=True forces execution (ignores freshness).
        @athena: e731a461bdff
        """
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
            task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, "", task.deps)
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Execute with only=True
            statuses = executor.execute_task("build", only=True)

            # Verify task was executed despite being fresh (only implies force)
            self.assertEqual(mock_run.call_count, 1)
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "forced")


class TestMultilineExecution(unittest.TestCase):
    """
    Test multi-line command execution via temp files.
    @athena: ab0ba143da41
    """

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_single_line_command_uses_shell(self, mock_chmod, mock_run):
        """
        Test single-line commands execute via unified script execution.
        @athena: 39c1c27db0db
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify command was passed as script path
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args[0][0]
            script_path = call_args[0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))
            # Verify shell=True is NOT used (we invoke shell via shebang)
            call_kwargs = mock_run.call_args[1]
            self.assertFalse(call_kwargs.get("shell", False))

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_folded_block_uses_single_line_execution(self, mock_chmod, mock_run):
        """
        Test that YAML folded blocks (>) execute via unified script execution.
        @athena: da835b76999d
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Simulate a folded block command (has trailing newline but no internal ones)
            folded_cmd = "gcc -o bin/app src/*.c -I include\n"

            tasks = {"build": Task(name="build", cmd=folded_cmd)}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)
            executor.execute_task("build")

            # Should use unified script execution
            call_args = mock_run.call_args[0][0]
            script_path = call_args[0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

    @patch("subprocess.run")
    def test_multiline_command_uses_temp_file(self, mock_run):
        """
        Test multi-line commands execute via temporary script file.
        @athena: 8b68560c87e5
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            multiline_cmd = """echo line1
echo line2
echo line3"""

            tasks = {"build": Task(name="build", cmd=multiline_cmd)}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify subprocess was called with script path (not shell=True)
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args[0]
            call_kwargs = mock_run.call_args[1]

            # Should be called with list [script_path], not string
            self.assertIsInstance(call_args[0], list)
            self.assertFalse(call_kwargs.get("shell", False))

    def test_multiline_command_content(self):
        """
        Test multi-line command content is written to temp file.
        @athena: 86b1e417b4c3
        """
        import platform

        # Skip on Windows (different shell syntax)
        if platform.system() == "Windows":
            self.skipTest("Skipping on Windows - different shell syntax")

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Use relative path for output
            multiline_cmd = """echo "line1" > output.txt
echo "line2" >> output.txt
echo "line3" >> output.txt"""

            tasks = {"build": Task(name="build", cmd=multiline_cmd)}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            # Let the command actually run (no mocking)
            executor.execute_task("build")

            # Verify output file was created with all three lines
            output_file = project_root / "output.txt"
            self.assertTrue(output_file.exists())
            content = output_file.read_text()
            self.assertIn("line1", content)
            self.assertIn("line2", content)
            self.assertIn("line3", content)


class TestEnvironmentResolution(unittest.TestCase):
    """
    Test environment resolution and usage.
    @athena: a5e234d0d4bc
    """

    def test_get_effective_env_with_global_override(self):
        """
        Test that global_env_override takes precedence.
        @athena: 0a0b4871c035
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Create environments
            from tasktree.parser import Environment

            envs = {
                "prod": Environment(name="prod", shell="sh", args=["-c"]),
                "dev": Environment(name="dev", shell="bash", args=["-c"]),
            }

            # Create task with explicit env and recipe with default_env
            tasks = {"build": Task(name="build", cmd="echo hello", env="dev")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                environments=envs,
                default_env="dev",
                global_env_override="prod",  # Global override
            )
            executor = Executor(recipe, state_manager)

            # Global override should win
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "prod")

    def test_get_effective_env_with_task_env(self):
        """
        Test that task.env is used when no global override.
        @athena: 87c60056c58d
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Environment

            envs = {
                "prod": Environment(name="prod", shell="sh", args=["-c"]),
                "dev": Environment(name="dev", shell="bash", args=["-c"]),
            }

            tasks = {"build": Task(name="build", cmd="echo hello", env="dev")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                environments=envs,
                default_env="prod",
            )
            executor = Executor(recipe, state_manager)

            # Task env should win over default_env
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "dev")

    def test_get_effective_env_with_default_env(self):
        """
        Test that default_env is used when task has no explicit env.
        @athena: 4e169f47c686
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Environment

            envs = {"prod": Environment(name="prod", shell="sh", args=["-c"])}

            tasks = {"build": Task(name="build", cmd="echo hello")}  # No env
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                environments=envs,
                default_env="prod",
            )
            executor = Executor(recipe, state_manager)

            # Default env should be used
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "prod")

    def test_get_effective_env_platform_default(self):
        """
        Test that empty string is returned for platform default.
        @athena: 8e6f858e061c
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            # No envs defined, should return empty string
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "")

    def test_resolve_environment_with_custom_env(self):
        """
        Test resolving environment with custom shell and args.
        @athena: 82fd09bacad8
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Environment

            envs = {
                "zsh_env": Environment(
                    name="zsh_env", shell="zsh", args=["-c"], preamble="set -e\n"
                )
            }

            tasks = {"build": Task(name="build", cmd="echo hello", env="zsh_env")}
            recipe = Recipe(
                tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml", environments=envs
            )
            executor = Executor(recipe, state_manager)

            shell, args, preamble = executor._resolve_environment(tasks["build"])
            self.assertEqual(shell, "zsh")
            self.assertEqual(args, ["-c"])
            self.assertEqual(preamble, "set -e\n")

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_task_execution_uses_custom_shell(self, mock_chmod, mock_run):
        """
        Test that custom shell from environment is used for execution.
        @athena: b4778e6d1c52
        """
        import platform

        captured_script_content = []

        def capture_script_content(*args, **kwargs):
            # Read the script before subprocess.run returns
            script_path = args[0][0]
            with open(script_path, 'r') as f:
                captured_script_content.append(f.read())
            return MagicMock(returncode=0)

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Environment

            envs = {"fish": Environment(name="fish", shell="fish", args=["-c"])}

            tasks = {"build": Task(name="build", cmd="echo hello", env="fish")}
            recipe = Recipe(
                tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml", environments=envs
            )
            executor = Executor(recipe, state_manager)

            mock_run.side_effect = capture_script_content
            executor.execute_task("build")

            # Verify script execution was used and contains fish shell
            self.assertEqual(len(captured_script_content), 1)
            script_content = captured_script_content[0]

            # Read the script to verify it uses fish shell
            if not platform.system() == "Windows":
                self.assertIn("fish", script_content)

    def test_hash_changes_with_environment(self):
        """
        Test that task hash changes when environment changes.
        @athena: b54e9f49a005
        """
        from tasktree.hasher import hash_task

        # Same task, different environments
        hash1 = hash_task("echo hello", [], ".", [], "prod")
        hash2 = hash_task("echo hello", [], ".", [], "dev")
        hash3 = hash_task("echo hello", [], ".", [], "")

        # All hashes should be different
        self.assertNotEqual(hash1, hash2)
        self.assertNotEqual(hash2, hash3)
        self.assertNotEqual(hash1, hash3)

    @patch("subprocess.run")
    @patch("os.chmod")
    def test_run_task_substitutes_environment_variables(self, mock_chmod, mock_run):
        """
        Test that _run_task substitutes environment variables.
        @athena: 5d62ad3e3913
        """
        os.environ['TEST_ENV_VAR'] = 'test_value'
        captured_script_content = []

        def capture_script_content(*args, **kwargs):
            # Read the script before subprocess.run returns
            script_path = args[0][0]
            with open(script_path, 'r') as f:
                captured_script_content.append(f.read())
            return MagicMock(returncode=0)

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                state_manager = StateManager(project_root)

                # Create task with env placeholder
                tasks = {"test": Task(
                    name="test",
                    cmd="echo {{ env.TEST_ENV_VAR }}",
                    working_dir=".",
                )}
                recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
                executor = Executor(recipe, state_manager)

                mock_run.side_effect = capture_script_content
                executor._run_task(tasks["test"], {})

                # Verify command has env var substituted in the script
                self.assertEqual(len(captured_script_content), 1)
                script_content = captured_script_content[0]
                self.assertIn('test_value', script_content)
                self.assertNotIn('{{ env.TEST_ENV_VAR }}', script_content)
        finally:
            del os.environ['TEST_ENV_VAR']

    @patch("subprocess.run")
    def test_run_task_env_substitution_in_working_dir(self, mock_run):
        """
        Test environment variables work in working_dir.
        @athena: a2d488c3e905
        """
        os.environ['SUBDIR'] = 'mydir'
        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                state_manager = StateManager(project_root)

                # Create subdirectory
                (project_root / 'mydir').mkdir()

                tasks = {"test": Task(
                    name="test",
                    cmd="echo test",
                    working_dir="{{ env.SUBDIR }}",
                )}
                recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
                executor = Executor(recipe, state_manager)

                mock_run.return_value = MagicMock(returncode=0)
                executor._run_task(tasks["test"], {})

                # Verify working_dir was substituted
                called_cwd = mock_run.call_args[1]['cwd']
                self.assertEqual(called_cwd, project_root / 'mydir')
        finally:
            del os.environ['SUBDIR']

    def test_run_task_undefined_env_var_raises(self):
        """
        Test undefined environment variable raises clear error.
        @athena: 4d17d3e6e7e9
        """
        # Ensure var is not set
        if 'UNDEFINED_TEST_VAR' in os.environ:
            del os.environ['UNDEFINED_TEST_VAR']

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            tasks = {"test": Task(
                name="test",
                cmd="echo {{ env.UNDEFINED_TEST_VAR }}",
                working_dir=".",
            )}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            executor = Executor(recipe, state_manager)

            with self.assertRaises(ValueError) as cm:
                executor._run_task(tasks["test"], {})

            self.assertIn("UNDEFINED_TEST_VAR", str(cm.exception))
            self.assertIn("not set", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
