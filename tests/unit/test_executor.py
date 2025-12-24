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

            # Verify subprocess was called with shell + args + command
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            # Command should be passed as [shell, shell_arg, cmd]
            self.assertEqual(call_args[0][0], ["bash", "-c", "cargo build"])

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

            # Verify command had arguments substituted and passed as [shell, shell_arg, cmd]
            call_args = mock_run.call_args
            self.assertEqual(call_args[0][0], ["bash", "-c", "echo Deploying to production"])


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
        """Test error when working directory doesn't exist."""
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
        """Test error when command doesn't exist."""
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


class TestOnlyMode(unittest.TestCase):
    """Test the --only mode that skips dependencies."""

    @patch("subprocess.run")
    def test_only_mode_skips_dependencies(self, mock_run):
        """Test that only=True executes only the target task, not dependencies."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="echo linting"),
                "build": Task(name="build", cmd="echo building", deps=["lint"]),
            }
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Execute with only=True
            statuses = executor.execute_task("build", only=True)

            # Verify only build was executed, not lint
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args
            self.assertEqual(call_args[0][0], ["bash", "-c", "echo building"])

            # Verify statuses only contains the target task
            self.assertEqual(len(statuses), 1)
            self.assertIn("build", statuses)
            self.assertNotIn("lint", statuses)

    @patch("subprocess.run")
    def test_only_mode_with_multiple_dependencies(self, mock_run):
        """Test that only=True skips all dependencies in a chain."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="echo linting"),
                "build": Task(name="build", cmd="echo building", deps=["lint"]),
                "test": Task(name="test", cmd="echo testing", deps=["build"]),
            }
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            # Execute test with only=True
            statuses = executor.execute_task("test", only=True)

            # Verify only test was executed
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args
            self.assertEqual(call_args[0][0], ["bash", "-c", "echo testing"])

            # Verify statuses only contains test
            self.assertEqual(len(statuses), 1)
            self.assertIn("test", statuses)
            self.assertNotIn("build", statuses)
            self.assertNotIn("lint", statuses)

    @patch("subprocess.run")
    def test_only_mode_forces_execution(self, mock_run):
        """Test that only=True forces execution (ignores freshness)."""
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

            mock_run.return_value = MagicMock(returncode=0)

            # Execute with only=True
            statuses = executor.execute_task("build", only=True)

            # Verify task was executed despite being fresh (only implies force)
            self.assertEqual(mock_run.call_count, 1)
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "forced")


class TestMultilineExecution(unittest.TestCase):
    """Test multi-line command execution via temp files."""

    @patch("subprocess.run")
    def test_single_line_command_uses_shell(self, mock_run):
        """Test single-line commands execute via shell invocation."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)

            executor.execute_task("build")

            # Verify command was passed as [shell, shell_arg, cmd]
            self.assertEqual(mock_run.call_count, 1)
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args, ["bash", "-c", "echo hello"])
            # Verify shell=True is NOT used (we invoke shell explicitly)
            call_kwargs = mock_run.call_args[1]
            self.assertFalse(call_kwargs.get("shell", False))

    @patch("subprocess.run")
    def test_folded_block_uses_single_line_execution(self, mock_run):
        """Test that YAML folded blocks (>) are treated as single-line commands."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Simulate a folded block command (has trailing newline but no internal ones)
            folded_cmd = "gcc -o bin/app src/*.c -I include\n"

            tasks = {"build": Task(name="build", cmd=folded_cmd)}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)
            executor.execute_task("build")

            # Should use single-line execution (shell + args + cmd)
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args, ["bash", "-c", folded_cmd])

    @patch("subprocess.run")
    def test_multiline_command_uses_temp_file(self, mock_run):
        """Test multi-line commands execute via temporary script file."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            multiline_cmd = """echo line1
echo line2
echo line3"""

            tasks = {"build": Task(name="build", cmd=multiline_cmd)}
            recipe = Recipe(tasks=tasks, project_root=project_root)
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
        """Test multi-line command content is written to temp file."""
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
            recipe = Recipe(tasks=tasks, project_root=project_root)
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
    """Test environment resolution and usage."""

    def test_get_effective_env_with_global_override(self):
        """Test that global_env_override takes precedence."""
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
                environments=envs,
                default_env="dev",
                global_env_override="prod",  # Global override
            )
            executor = Executor(recipe, state_manager)

            # Global override should win
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "prod")

    def test_get_effective_env_with_task_env(self):
        """Test that task.env is used when no global override."""
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
                environments=envs,
                default_env="prod",
            )
            executor = Executor(recipe, state_manager)

            # Task env should win over default_env
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "dev")

    def test_get_effective_env_with_default_env(self):
        """Test that default_env is used when task has no explicit env."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Environment

            envs = {"prod": Environment(name="prod", shell="sh", args=["-c"])}

            tasks = {"build": Task(name="build", cmd="echo hello")}  # No env
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                environments=envs,
                default_env="prod",
            )
            executor = Executor(recipe, state_manager)

            # Default env should be used
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "prod")

    def test_get_effective_env_platform_default(self):
        """Test that empty string is returned for platform default."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(tasks=tasks, project_root=project_root)
            executor = Executor(recipe, state_manager)

            # No envs defined, should return empty string
            env_name = executor._get_effective_env_name(tasks["build"])
            self.assertEqual(env_name, "")

    def test_resolve_environment_with_custom_env(self):
        """Test resolving environment with custom shell and args."""
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
                tasks=tasks, project_root=project_root, environments=envs
            )
            executor = Executor(recipe, state_manager)

            shell, args, preamble = executor._resolve_environment(tasks["build"])
            self.assertEqual(shell, "zsh")
            self.assertEqual(args, ["-c"])
            self.assertEqual(preamble, "set -e\n")

    @patch("subprocess.run")
    def test_task_execution_uses_custom_shell(self, mock_run):
        """Test that custom shell from environment is used for execution."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Environment

            envs = {"fish": Environment(name="fish", shell="fish", args=["-c"])}

            tasks = {"build": Task(name="build", cmd="echo hello", env="fish")}
            recipe = Recipe(
                tasks=tasks, project_root=project_root, environments=envs
            )
            executor = Executor(recipe, state_manager)

            mock_run.return_value = MagicMock(returncode=0)
            executor.execute_task("build")

            # Verify fish shell was used
            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args, ["fish", "-c", "echo hello"])

    def test_hash_changes_with_environment(self):
        """Test that task hash changes when environment changes."""
        from tasktree.hasher import hash_task

        # Same task, different environments
        hash1 = hash_task("echo hello", [], ".", [], "prod")
        hash2 = hash_task("echo hello", [], ".", [], "dev")
        hash3 = hash_task("echo hello", [], ".", [], "")

        # All hashes should be different
        self.assertNotEqual(hash1, hash2)
        self.assertNotEqual(hash2, hash3)
        self.assertNotEqual(hash1, hash3)


if __name__ == "__main__":
    unittest.main()
