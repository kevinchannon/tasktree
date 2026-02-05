"""Tests for executor module."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch, call

from helpers.logging import logger_stub
from tasktree.executor import Executor
from tasktree.parser import Recipe, Task
from tasktree.process_runner import ProcessRunner, TaskOutputTypes, make_process_runner
from tasktree.state import StateManager, TaskState


class TestTaskStatus(unittest.TestCase):
    """
    @athena: 29bc4b565149
    """

    def test_check_never_run(self):
        """
        Test status for task that has never run.
        @athena: db5a0f68dacc
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "build": Task(name="build", cmd="cargo build", outputs=["target/bin"])
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            status = executor.check_task_status(
                tasks["build"],
                {},
                make_process_runner(TaskOutputTypes.ALL, logger_stub),
                False,
            )
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "never_run")

    def test_check_no_outputs(self):
        """
        Test status for task with no inputs and no outputs (always runs).
        @athena: fdaca0ac4e9f
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="cargo test")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(
                tasks["test"], {}, process_runner, False
            )
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "no_outputs")

    def test_check_fresh(self):
        """
        Test status for task that is fresh.
        @athena: 167b3e9937e4
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

            task = Task(
                name="build",
                cmd="cat input.txt",
                inputs=["input.txt"],
                outputs=["output.txt"],
            )
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            # Set state with current mtime
            current_mtime = input_file.stat().st_mtime
            state_manager.set(
                cache_key,
                TaskState(
                    last_run=time.time(), input_state={"input.txt": current_mtime}
                ),
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            status = executor.check_task_status(
                task, {}, make_process_runner(TaskOutputTypes.ALL, logger_stub)
            )
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")


class TestExecutor(unittest.TestCase):
    """
    @athena: 2b01be6f3e51
    """

    @patch("os.chmod")
    def test_execute_simple_task(self, _chmod_fake):
        """
        Test executing a simple task.
        @athena: 6ba5a319dd19
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"build": Task(name="build", cmd="cargo build")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            ).execute_task("build", TaskOutputTypes.ALL)

            # Verify subprocess was called with a script path
            process_runner_spy.run.assert_called_once()
            call_args = process_runner_spy.run.call_args
            # Command should be passed as [script_path]
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

    def test_execute_with_dependencies(self):
        """
        Test executing task with dependencies.
        @athena: bd3de7c1bb8c
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="cargo clippy"),
                "build": Task(name="build", cmd="cargo build", deps=["lint"]),
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            ).execute_task("build", TaskOutputTypes.ALL)

            # Verify both tasks were executed
            self.assertEqual(process_runner_spy.run.call_count, 2)

    @patch("os.chmod")
    def test_execute_with_args(self, _fake_chmod):
        """
        Test executing task with arguments.
        @athena: a4ec6b06333f
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
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            executor = Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            )

            executor.execute_task(
                "deploy", TaskOutputTypes.ALL, {"environment": "production"}
            )

            # Verify command had arguments substituted and passed as script
            call_args = process_runner_spy.run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

    @patch("os.chmod")
    @patch("os.unlink")
    def test_run_command_as_script_single_line(self, mock_unlink, mock_chmod):
        """
        Test _run_command_as_script with single-line command.
        @athena: 791553a2ae01
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            process_runner_spy = MagicMock(spec=ProcessRunner)

            # Call the unified method directly
            executor._run_command_as_script(
                cmd="echo hello",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble="",
                process_runner=process_runner_spy,
            )

            # Verify subprocess.run was called with a script path
            process_runner_spy.run.assert_called_once()
            call_args = process_runner_spy.run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh"))

            # Verify chmod was called to make script executable
            mock_chmod.assert_called_once()

            # Verify cleanup (unlink) was called
            mock_unlink.assert_called_once()

    @patch("os.chmod")
    @patch("os.unlink")
    def test_run_command_as_script_with_preamble(self, unlink_spy, chmod_spy):
        """
        Test _run_command_as_script with preamble.
        @athena: fcb783aa3c67
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner_spy = MagicMock(spec=ProcessRunner)

            # Call with preamble
            executor._run_command_as_script(
                cmd="echo hello",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble="set -e\n",
                process_runner=process_runner_spy,
            )

            process_runner_spy.run.assert_called_once()
            chmod_spy.assert_called_once()
            unlink_spy.assert_called_once()

    @patch("os.chmod")
    @patch("os.unlink")
    def test_run_command_as_script_multiline(self, unlink_spy, chmod_spy):
        """
        Test _run_command_as_script with multi-line command.
        @athena: c7500eea58e2
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello\necho world")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            process_runner_spy = MagicMock(spec=ProcessRunner)

            executor._run_command_as_script(
                cmd="echo hello\necho world",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble="",
                process_runner=process_runner_spy,
            )

            process_runner_spy.run.assert_called_once()
            chmod_spy.assert_called_once()
            unlink_spy.assert_called_once()

    def test_run_command_as_script_comprehensive_validation(self):
        """
        Comprehensive test validating script creation, permissions, content, and execution order.

        This test validates:
        1. Script is created with correct name/suffix
        2. Script is made executable with chmod
        3. Script content has correct ordering (shebang -> preamble -> command)
        4. ProcessRunner is called AFTER all script setup completes
        @athena: 4eec41b394ec
        """

        import platform
        import stat

        # Skip on Windows (different execution model)
        if platform.system() == "Windows":
            self.skipTest("Skipping on Windows - different script handling")

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo hello\necho world")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Track all operations in order
            call_order = []
            captured_script_path = None
            captured_script_content = None
            captured_chmod_path = None
            captured_chmod_mode = None

            # Mock os.chmod to capture permissions and script path
            original_chmod = os.chmod

            def mock_chmod_func(path, mode):
                nonlocal \
                    captured_chmod_path, \
                    captured_chmod_mode, \
                    captured_script_path, \
                    captured_script_content
                call_order.append("chmod")
                captured_chmod_path = str(path)
                captured_chmod_mode = mode
                captured_script_path = str(path)
                # Read the script content at this point (before it gets executed and deleted)
                with open(path, "r") as f:
                    captured_script_content = f.read()
                return original_chmod(path, mode)

            # Mock subprocess.run to capture when it's called
            def mock_subprocess_run(*args, **kwargs):
                call_order.append("subprocess.run")
                # Verify the script still exists at this point
                if captured_script_path:
                    script_path = args[0][0]
                    self.assertTrue(
                        Path(script_path).exists(),
                        "Script should exist when subprocess.run is called",
                    )
                return MagicMock(returncode=0)

            # Create process runner for test
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            # Apply patches
            with patch("os.chmod", side_effect=mock_chmod_func):
                with patch("subprocess.run", side_effect=mock_subprocess_run):
                    executor._run_command_as_script(
                        cmd="echo hello\necho world",
                        working_dir=project_root,
                        task_name="test",
                        shell="bash",
                        preamble="set -e\n",
                        process_runner=process_runner,
                    )

            # Requirement 1: Verify script was created with correct suffix
            self.assertIsNotNone(captured_script_path, "Script path should be captured")
            self.assertTrue(
                captured_script_path.endswith(".sh"),
                f"Script should have .sh suffix, got: {captured_script_path}",
            )

            # Requirement 2: Verify script was made executable
            self.assertIsNotNone(captured_chmod_path, "chmod should have been called")
            self.assertEqual(
                captured_script_path,
                captured_chmod_path,
                "chmod should be called on the script file",
            )
            # Verify executable bit is set
            self.assertIsNotNone(captured_chmod_mode, "chmod mode should be captured")
            self.assertTrue(
                captured_chmod_mode & stat.S_IEXEC,
                f"Script should have executable permission bit set, got mode: {oct(captured_chmod_mode)}",
            )

            # Requirement 3: Verify script content has correct ordering
            self.assertIsNotNone(
                captured_script_content, "Script content should be captured"
            )
            lines = captured_script_content.split("\n")
            self.assertGreaterEqual(
                len(lines),
                3,
                "Script should have at least shebang, preamble, and command",
            )

            # Check shebang is first
            self.assertTrue(
                lines[0].startswith("#!/usr/bin/env bash"),
                f"First line should be shebang, got: {lines[0]}",
            )

            # Check preamble comes after shebang
            self.assertIn(
                "set -e",
                captured_script_content,
                "Preamble should be in script content",
            )

            # Check command comes after preamble
            self.assertIn(
                "echo hello", captured_script_content, "Command should be in script"
            )
            self.assertIn(
                "echo world", captured_script_content, "Command should be in script"
            )

            # Verify order: shebang before preamble before command
            shebang_idx = captured_script_content.find("#!/usr/bin/env bash")
            preamble_idx = captured_script_content.find("set -e")
            command_idx = captured_script_content.find("echo hello")

            self.assertLess(
                shebang_idx, preamble_idx, "Shebang should come before preamble"
            )
            self.assertLess(
                preamble_idx, command_idx, "Preamble should come before command"
            )

            # Requirement 4: Verify subprocess.run called AFTER all setup
            self.assertIn("chmod", call_order, "chmod should be called")
            self.assertIn(
                "subprocess.run", call_order, "subprocess.run should be called"
            )

            # Verify ordering: chmod should come before subprocess.run
            chmod_idx = call_order.index("chmod")
            subprocess_idx = call_order.index("subprocess.run")

            self.assertLess(
                chmod_idx, subprocess_idx, "chmod should come before subprocess.run"
            )


class TestMissingOutputs(unittest.TestCase):
    """
    @athena: 6f72f170894d
    """

    def test_fresh_task_with_all_outputs_present(self):
        """
        Test that fresh task with all outputs present should skip.
        @athena: 529abcc7d9dd
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
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")

    def test_fresh_task_with_missing_output(self):
        """
        Test that fresh task with missing output should run with outputs_missing reason.
        @athena: 1061f2d5c1ac
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
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")
            self.assertEqual(status.changed_files, ["output.txt"])

    def test_fresh_task_with_partial_outputs(self):
        """
        Test that task with some outputs present but not all should run.
        @athena: a04a60bd9058
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
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")
            self.assertIn("output2.txt", status.changed_files)

    def test_task_with_no_state_should_not_warn_about_outputs(self):
        """
        Test that first run (no state) uses never_run reason, not outputs_missing.
        @athena: 3612805f025c
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
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "never_run")  # Not outputs_missing

    def test_task_with_no_outputs_unaffected(self):
        """
        Test that tasks with no outputs declared are unaffected.
        @athena: 027e040b2197
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            task = Task(name="test", cmd="echo test")  # No outputs

            tasks = {"test": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "no_outputs")  # Always runs

    def test_output_glob_pattern_with_working_dir(self):
        """
        Test that output patterns resolve correctly with working_dir.
        @athena: fcc6b56d0c6e
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
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertFalse(status.will_run)
            self.assertEqual(status.reason, "fresh")

    def test_output_glob_pattern_no_matches(self):
        """
        Test that glob pattern with zero matches triggers re-run.
        @athena: 58a7173dda57
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
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"package": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            status = executor.check_task_status(task, {}, process_runner)
            self.assertTrue(status.will_run)
            self.assertEqual(status.reason, "outputs_missing")


class TestExecutorErrors(unittest.TestCase):
    """
    Tests for executor error conditions.
    @athena: bf8665e80bc1
    """

    def test_execute_subprocess_failure(self):
        """
        Test ExecutionError raised when subprocess fails.
        @athena: cb9a84ded9db
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  fail:
    cmd: exit 1
""")

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            with self.assertRaises(ExecutionError) as cm:
                executor.execute_task("fail", TaskOutputTypes.ALL, {})
            self.assertIn("exit code", str(cm.exception).lower())

    def test_execute_working_dir_not_found(self):
        """
        Test error when working directory doesn't exist.
        @athena: b4f1caa74569
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  test:
    working_dir: nonexistent_directory
    cmd: echo "test"
""")

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            with self.assertRaises((ExecutionError, FileNotFoundError, OSError)):
                executor.execute_task("test", TaskOutputTypes.ALL, {})

    def test_execute_command_not_found(self):
        """
        Test error when command doesn't exist.
        @athena: 3e875ac776cd
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  test:
    cmd: nonexistent_command_12345
""")

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            with self.assertRaises(ExecutionError):
                executor.execute_task("test", TaskOutputTypes.ALL, {})

    def test_execute_permission_denied(self):
        """
        Test error when command not executable.
        @athena: 8eea756b0384
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a script file without execute permissions
            script_path = project_root / "script.sh"
            script_path.write_text("#!/bin/bash\necho test")
            script_path.chmod(0o644)  # Read/write but not execute

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text(f"""
tasks:
  test:
    cmd: {script_path}
""")

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            with self.assertRaises((ExecutionError, PermissionError, OSError)):
                executor.execute_task("test", TaskOutputTypes.ALL, {})

    def test_builtin_working_dir_in_working_dir_raises_error(self):
        """
        Test that using {{ tt.working_dir }} in working_dir raises clear error.
        @athena: 45c005938b3b
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  test:
    working_dir: "{{ tt.working_dir }}/subdir"
    cmd: echo "test"
""")

            from tasktree.executor import ExecutionError, Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            with self.assertRaises(ExecutionError) as cm:
                executor.execute_task("test", TaskOutputTypes.ALL, {})

            error_msg = str(cm.exception)
            self.assertIn("Cannot use {{ tt.working_dir }}", error_msg)
            self.assertIn("circular dependency", error_msg)

    def test_other_builtin_vars_in_working_dir_allowed(self):
        """
        Test that non-circular builtin vars like {{ tt.task_name }} work in working_dir.
        @athena: 5784b8718ffb
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create directory using task name
            task_subdir = project_root / "test-task"
            task_subdir.mkdir()

            recipe_path = project_root / "tasktree.yaml"
            recipe_path.write_text("""
tasks:
  test-task:
    working_dir: "{{ tt.task_name }}"
    cmd: pwd
""")

            from tasktree.executor import Executor
            from tasktree.parser import parse_recipe
            from tasktree.state import StateManager

            recipe = parse_recipe(recipe_path)
            state_manager = StateManager(project_root)
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Should not raise - tt.task_name is allowed in working_dir
            executor.execute_task("test-task", TaskOutputTypes.ALL, {})


class TestExecutorPrivateMethods(unittest.TestCase):
    """
    Tests for executor private methods.
    @athena: 123409a3a7f2
    """

    def test_substitute_args_single(self):
        """
        Test substituting single argument.
        @athena: 9b1dfb1be1a3
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"deploy": Task(name="deploy", cmd="echo {{ arg.environment }}")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            result = executor._substitute_args(
                "echo {{ arg.environment }}", {"environment": "production"}
            )
            self.assertEqual(result, "echo production")

    def test_substitute_args_multiple(self):
        """
        Test substituting multiple arguments.
        @athena: a81621d02422
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "deploy": Task(
                    name="deploy", cmd="deploy {{ arg.app }} to {{ arg.region }}"
                )
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            result = executor._substitute_args(
                "deploy {{ arg.app }} to {{ arg.region }}",
                {"app": "myapp", "region": "us-east-1"},
            )
            self.assertEqual(result, "deploy myapp to us-east-1")

    def test_substitute_args_missing_placeholder(self):
        """
        Test raises error when arg not provided.
        @athena: fe8094a00805
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "deploy": Task(
                    name="deploy", cmd="echo {{ arg.environment }} {{ arg.missing }}"
                )
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Missing argument should raise ValueError
            with self.assertRaises(ValueError) as cm:
                executor._substitute_args(
                    "echo {{ arg.environment }} {{ arg.missing }}",
                    {"environment": "production"},
                )
            self.assertIn("missing", str(cm.exception))
            self.assertIn("not defined", str(cm.exception))

    def test_check_inputs_changed_mtime(self):
        """
        Test detects changed file by mtime.
        @athena: ad1eef94f9a4
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
                input_state={"input.txt": original_mtime - 100},  # Older mtime
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Check if inputs changed
            changed = executor._check_inputs_changed(task, cached_state, ["input.txt"])

            # Should detect change because current mtime > cached mtime
            self.assertEqual(changed, ["input.txt"])

    def test_check_outputs_missing(self):
        """
        Test detects missing output files.
        @athena: 68398c9cfcd9
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Task declares outputs but files don't exist
            task = Task(
                name="build", cmd="echo test > output.txt", outputs=["output.txt"]
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Check for missing outputs
            missing = executor._check_outputs_missing(task)

            # Should detect output.txt is missing
            self.assertEqual(missing, ["output.txt"])

    def test_expand_globs_multiple_patterns(self):
        """
        Test expanding multiple glob patterns.
        @athena: 27094d19d541
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create test files
            (project_root / "file1.txt").write_text("test1")
            (project_root / "file2.txt").write_text("test2")
            (project_root / "script.py").write_text("print('test')")

            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo test")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Expand multiple patterns
            result = executor._expand_globs(["*.txt", "*.py"], ".")

            # Should find all matching files
            self.assertEqual(set(result), {"file1.txt", "file2.txt", "script.py"})


class TestOnlyMode(unittest.TestCase):
    """
    Test the --only mode that skips dependencies.
    @athena: 9b470eafd594
    """

    @patch("os.chmod")
    def test_only_mode_skips_dependencies(self, _fake_chmod):
        """
        Test that only=True executes only the target task, not dependencies.
        @athena: 88af1cf22c38
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="echo linting"),
                "build": Task(name="build", cmd="echo building", deps=["lint"]),
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            # Execute with only=True
            statuses = Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            ).execute_task("build", TaskOutputTypes.ALL, only=True)

            # Verify only build was executed, not lint
            self.assertEqual(process_runner_spy.run.call_count, 1)
            call_args = process_runner_spy.run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

            # Verify statuses only contains the target task
            self.assertEqual(len(statuses), 1)
            self.assertIn("build", statuses)
            self.assertNotIn("lint", statuses)

    @patch("os.chmod")
    def test_only_mode_with_multiple_dependencies(self, _fake_chmod):
        """
        Test that only=True skips all dependencies in a chain.
        @athena: c6ba6d4a8fb8
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "lint": Task(name="lint", cmd="echo linting"),
                "build": Task(name="build", cmd="echo building", deps=["lint"]),
                "test": Task(name="test", cmd="echo testing", deps=["build"]),
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            process_runner_spy = MagicMock(spec=ProcessRunner)
            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            # Execute test with only=True
            statuses = Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            ).execute_task("test", TaskOutputTypes.ALL, only=True)

            # Verify only test was executed
            self.assertEqual(process_runner_spy.run.call_count, 1)
            call_args = process_runner_spy.run.call_args
            script_path = call_args[0][0][0]
            self.assertTrue(script_path.endswith(".sh") or script_path.endswith(".bat"))

            # Verify statuses only contains test
            self.assertEqual(len(statuses), 1)
            self.assertIn("test", statuses)
            self.assertNotIn("build", statuses)
            self.assertNotIn("lint", statuses)

    def test_only_mode_forces_execution(self):
        """
        Test that only=True forces execution (ignores freshness).
        @athena: 87fd4889aa19
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
            task_hash = hash_task(
                task.cmd, task.outputs, task.working_dir, task.args, "__platform_default__", task.deps
            )
            cache_key = make_cache_key(task_hash)

            # Set state with recent run
            state_manager.set(
                cache_key,
                TaskState(last_run=time.time(), input_state={}),
            )

            tasks = {"build": task}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            # Execute with only=True
            statuses = Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            ).execute_task("build", TaskOutputTypes.ALL, only=True)

            # Verify task was executed despite being fresh (only implies force)
            self.assertEqual(process_runner_spy.run.call_count, 1)
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "forced")


class TestMultilineExecution(unittest.TestCase):
    """
    Test multi-line command execution via temp files.
    @athena: f5503e728b34
    """

    def test_multiline_command_content(self):
        """
        Test multi-line command content is written to temp file.
        @athena: 939862eef5d8
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
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Let the command actually run (no mocking)
            executor.execute_task("build", TaskOutputTypes.ALL)

            # Verify output file was created with all three lines
            output_file = project_root / "output.txt"
            self.assertTrue(output_file.exists())
            content = output_file.read_text()
            self.assertIn("line1", content)
            self.assertIn("line2", content)
            self.assertIn("line3", content)


class TestRunnerResolution(unittest.TestCase):
    """
    Test runner resolution and usage.
    @athena: 43e99504aef1
    """

    def test_get_effective_runner_with_global_override(self):
        """
        Test that global_runner_override takes precedence.
        @athena: f0071f4d55ba
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Create runners
            from tasktree.parser import Runner

            runners = {
                "prod": Runner(name="prod", shell="sh", args=["-c"]),
                "dev": Runner(name="dev", shell="bash", args=["-c"]),
            }

            # Create task with explicit run_in and recipe with default_runner
            tasks = {"build": Task(name="build", cmd="echo hello", run_in="dev")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners=runners,
                default_runner="dev",
                global_runner_override="prod",  # Global override
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Global override should win
            runner_name = executor._get_effective_runner_name(tasks["build"])
            self.assertEqual(runner_name, "prod")

    def test_get_effective_runner_with_task_runner(self):
        """
        Test that task.run_in is used when no global override.
        @athena: 50c636d4ee16
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Runner

            runners = {
                "prod": Runner(name="prod", shell="sh", args=["-c"]),
                "dev": Runner(name="dev", shell="bash", args=["-c"]),
            }

            tasks = {"build": Task(name="build", cmd="echo hello", run_in="dev")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners=runners,
                default_runner="prod",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Task runner should win over default_runner
            runner_name = executor._get_effective_runner_name(tasks["build"])
            self.assertEqual(runner_name, "dev")

    def test_get_effective_runner_with_default_runner(self):
        """
        Test that default_runner is used when task has no explicit run_in.
        @athena: 6372bb43f96b
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Runner

            runners = {"prod": Runner(name="prod", shell="sh", args=["-c"])}

            tasks = {"build": Task(name="build", cmd="echo hello")}  # No run_in
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners=runners,
                default_runner="prod",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Default runner should be used
            runner_name = executor._get_effective_runner_name(tasks["build"])
            self.assertEqual(runner_name, "prod")

    def test_get_effective_runner_platform_default(self):
        """
        Test that session default runner name is returned for platform default.
        @athena: 19260cca1cf9
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # No runners defined, should return session default runner name
            runner_name = executor._get_effective_runner_name(tasks["build"])
            self.assertEqual(runner_name, "__platform_default__")

    def test_resolve_runner_with_custom_runner(self):
        """
        Test resolving runner with custom shell and preamble.
        @athena: ad7409ace0a8
        """

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Runner

            runners = {
                "zsh_runner": Runner(
                    name="zsh_runner", shell="zsh", args=["-c"], preamble="set -e\n"
                )
            }

            tasks = {"build": Task(name="build", cmd="echo hello", run_in="zsh_runner")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners=runners,
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            shell, preamble = executor._resolve_runner(tasks["build"])
            self.assertEqual(shell, "zsh")
            self.assertEqual(preamble, "set -e\n")

    @patch("platform.system")
    def test_resolve_runner_falls_back_to_platform_default(self, mock_system):
        """
        Test that _resolve_runner falls back to platform defaults when no runner is defined.
        @athena: to-be-generated
        """
        # Test Unix/Linux platform
        mock_system.return_value = "Linux"

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # No runners defined, task has no run_in
            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={},  # No runners
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            shell, preamble = executor._resolve_runner(tasks["build"])
            self.assertEqual(shell, "bash")
            self.assertEqual(preamble, "")

        # Test Windows platform
        mock_system.return_value = "Windows"

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            tasks = {"build": Task(name="build", cmd="echo hello")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners={},
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            shell, preamble = executor._resolve_runner(tasks["build"])
            self.assertEqual(shell, "cmd")
            self.assertEqual(preamble, "")

    @patch("os.chmod")
    def test_task_execution_uses_custom_shell(self, _fake_chmod):
        """
        Test that custom shell from runner is used for execution.
        @athena: af5465f2617e
        """

        import platform

        captured_script_content = []

        def capture_script_content(*args, **kwargs):
            # Read the script before process runner returns
            script_path = args[0][0]
            with open(script_path, "r") as f:
                captured_script_content.append(f.read())
            return MagicMock(returncode=0)

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            from tasktree.parser import Runner

            runners = {"fish": Runner(name="fish", shell="fish", args=["-c"])}

            tasks = {"build": Task(name="build", cmd="echo hello", run_in="fish")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                runners=runners,
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            process_runner_spy.run.side_effect = capture_script_content

            fake_proc_runner_factory = MagicMock()
            fake_proc_runner_factory.return_value = process_runner_spy

            Executor(
                recipe, state_manager, logger_stub, fake_proc_runner_factory
            ).execute_task("build", TaskOutputTypes.ALL)

            # Verify script execution was used and contains fish shell
            self.assertEqual(len(captured_script_content), 1)
            script_content = captured_script_content[0]

            # Read the script to verify it uses fish shell
            if not platform.system() == "Windows":
                self.assertIn("fish", script_content)

    def test_hash_changes_with_runner(self):
        """
        Test that task hash changes when runner changes.
        @athena: b54e9f49a005
        """

        from tasktree.hasher import hash_task

        # Same task, different runners
        hash1 = hash_task("echo hello", [], ".", [], "prod")
        hash2 = hash_task("echo hello", [], ".", [], "dev")
        hash3 = hash_task("echo hello", [], ".", [], "")

        # All hashes should be different
        self.assertNotEqual(hash1, hash2)
        self.assertNotEqual(hash2, hash3)
        self.assertNotEqual(hash1, hash3)

    @patch("os.chmod")
    def test_run_task_substitutes_environment_variables(self, _fake_chmod):
        """
        Test that _run_task substitutes environment variables.
        @athena: 6ff1df5d470b
        """

        os.environ["TEST_ENV_VAR"] = "test_value"
        captured_script_content = []

        def capture_script_content(*args, **kwargs):
            # Read the script before subprocess.run returns
            script_path = args[0][0]
            with open(script_path, "r") as f:
                captured_script_content.append(f.read())
            return MagicMock(returncode=0)

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                state_manager = StateManager(project_root)

                # Create task with env placeholder
                tasks = {
                    "test": Task(
                        name="test",
                        cmd="echo {{ env.TEST_ENV_VAR }}",
                        working_dir=".",
                    )
                }
                recipe = Recipe(
                    tasks=tasks,
                    project_root=project_root,
                    recipe_path=project_root / "tasktree.yaml",
                )
                executor = Executor(
                    recipe, state_manager, logger_stub, make_process_runner
                )

                process_runner_spy = MagicMock(spec=ProcessRunner)
                process_runner_spy.run.side_effect = capture_script_content

                executor._run_task(tasks["test"], {}, process_runner_spy)

                # Verify command has env var substituted in the script
                self.assertEqual(len(captured_script_content), 1)
                script_content = captured_script_content[0]
                self.assertIn("test_value", script_content)
                self.assertNotIn("{{ env.TEST_ENV_VAR }}", script_content)
        finally:
            del os.environ["TEST_ENV_VAR"]

    def test_run_task_env_substitution_in_working_dir(self):
        """
        Test environment variables work in working_dir.
        @athena: 918844bd22d1
        """

        os.environ["SUBDIR"] = "mydir"
        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                state_manager = StateManager(project_root)

                # Create subdirectory
                (project_root / "mydir").mkdir()

                tasks = {
                    "test": Task(
                        name="test",
                        cmd="echo test",
                        working_dir="{{ env.SUBDIR }}",
                    )
                }
                recipe = Recipe(
                    tasks=tasks,
                    project_root=project_root,
                    recipe_path=project_root / "tasktree.yaml",
                )
                executor = Executor(
                    recipe, state_manager, logger_stub, make_process_runner
                )

                process_runner_spy = MagicMock(spec=ProcessRunner)
                executor._run_task(tasks["test"], {}, process_runner_spy)

                # Verify working_dir was substituted
                called_cwd = process_runner_spy.run.call_args[1]["cwd"]
                self.assertEqual(called_cwd, project_root / "mydir")
        finally:
            del os.environ["SUBDIR"]

    def test_run_task_undefined_env_var_raises(self):
        """
        Test undefined environment variable raises clear error.
        @athena: 164a338d8a37
        """

        # Ensure var is not set
        if "UNDEFINED_TEST_VAR" in os.environ:
            del os.environ["UNDEFINED_TEST_VAR"]

        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            tasks = {
                "test": Task(
                    name="test",
                    cmd="echo {{ env.UNDEFINED_TEST_VAR }}",
                    working_dir=".",
                )
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            with self.assertRaises(ValueError) as cm:
                executor._run_task(
                    tasks["test"],
                    {},
                    make_process_runner(TaskOutputTypes.ALL, logger_stub),
                )

            self.assertIn("UNDEFINED_TEST_VAR", str(cm.exception))
            self.assertIn("not set", str(cm.exception))


class TestTaskOutputParameter(unittest.TestCase):
    """
    Test task_output parameter handling in Executor.
    @athena: c15f20ce7913
    """

    def test_run_command_as_script_accesses_task_output_via_self(self):
        """
        Test that _run_command_as_script() can access task_output via self.
        @athena: 362bec700c36
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {"test": Task(name="test", cmd="echo test")}
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            executor = Executor(
                recipe,
                state_manager,
                logger_stub,
                make_process_runner,
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            process_runner_spy.run.return_value = MagicMock(returncode=0)

            executor._run_command_as_script(
                cmd="echo test",
                working_dir=project_root,
                task_name="test",
                shell="bash",
                preamble="",
                process_runner=process_runner_spy,
            )

            process_runner_spy.run.assert_called_once()

    def test_task_specific_task_output_types_is_respected(self):
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "test": Task(
                    name="test", cmd="echo test", task_output=TaskOutputTypes.ERR
                )
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_stub = MagicMock(spec=ProcessRunner)
            process_runner_stub.run.return_value = MagicMock(returncode=0)
            process_runner_factory_spy = MagicMock()
            process_runner_factory_spy.side_effect = lambda _1, _2: process_runner_stub

            Executor(
                recipe,
                state_manager,
                logger_stub,
                process_runner_factory_spy,
            ).execute_task("test", None)

            process_runner_factory_spy.assert_has_calls(
                [call(TaskOutputTypes.ERR, logger_stub)]
            )

    def test_task_cli_task_output_types_overrides_specific_value_is_respected(self):
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            tasks = {
                "test": Task(
                    name="test", cmd="echo test", task_output=TaskOutputTypes.ERR
                )
            }
            recipe = Recipe(
                tasks=tasks,
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_stub = MagicMock(spec=ProcessRunner)
            process_runner_stub.run.return_value = MagicMock(returncode=0)
            process_runner_factory_spy = MagicMock()
            process_runner_factory_spy.side_effect = lambda _1, _2: process_runner_stub

            Executor(
                recipe,
                state_manager,
                logger_stub,
                process_runner_factory_spy,
            ).execute_task("test", TaskOutputTypes.ALL)

            process_runner_factory_spy.assert_has_calls(
                [call(TaskOutputTypes.ALL, logger_stub)]
            )


class TestExecutorProcessRunner(unittest.TestCase):
    """
    Tests for Executor's process_runner_factory parameter.
    @athena: 1c0756739b33
    """

    def test_executor_uses_process_runner_in_run_task(self):
        """
        Executor calls process_runner_factory in _run_task.
        @athena: e8b033b6f187
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            task = Task(name="test", cmd="echo test")
            recipe = Recipe(
                tasks={"test": task},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            process_runner_spy = MagicMock(spec=ProcessRunner)
            process_runner_spy.run.return_value = MagicMock(returncode=0)

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            executor._run_task(task, {}, process_runner_spy)

            process_runner_spy.run.assert_called_once()

    def test_substitute_runner_fields_includes_extra_args(self):
        """
        Test that _substitute_builtin_in_runner substitutes variables in extra_args.
        """
        from tasktree.parser import Runner

        os.environ["MEMORY_LIMIT"] = "1024m"
        os.environ["CPU_LIMIT"] = "2"

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                state_manager = StateManager(project_root)

                recipe = Recipe(
                    tasks={},
                    project_root=project_root,
                    recipe_path=project_root / "tasktree.yaml",
                )
                executor = Executor(
                    recipe, state_manager, logger_stub, make_process_runner
                )

                # Create runner with variables in extra_args
                runner = Runner(
                    name="test",
                    dockerfile="Dockerfile",
                    context=".",
                    extra_args=[
                        "--memory={{ env.MEMORY_LIMIT }}",
                        "--cpus={{ env.CPU_LIMIT }}",
                        "--network=host",
                    ],
                )

                builtin_vars = {
                    "project_root": str(project_root),
                    "task_name": "test",
                }

                # Apply substitution
                substituted_runner = executor._substitute_builtin_in_runner(
                    runner, builtin_vars
                )

                # Verify substitution occurred
                self.assertEqual(
                    substituted_runner.extra_args,
                    ["--memory=1024m", "--cpus=2", "--network=host"],
                )
        finally:
            del os.environ["MEMORY_LIMIT"]
            del os.environ["CPU_LIMIT"]

    def test_substitute_runner_fields_includes_preamble_shell_dockerfile_context(self):
        """
        Test that _substitute_builtin_in_runner substitutes variables in preamble, shell, dockerfile, and context.
        """
        from tasktree.parser import Runner

        os.environ["BUILD_DIR"] = "docker"
        os.environ["CUSTOM_SHELL"] = "/bin/bash"

        try:
            with TemporaryDirectory() as tmpdir:
                project_root = Path(tmpdir)
                state_manager = StateManager(project_root)

                recipe = Recipe(
                    tasks={},
                    project_root=project_root,
                    recipe_path=project_root / "tasktree.yaml",
                )
                executor = Executor(
                    recipe, state_manager, logger_stub, make_process_runner
                )

                # Create runner with variables in preamble, shell, dockerfile, context
                runner = Runner(
                    name="test",
                    preamble="set -e\nexport BUILD_DIR={{ env.BUILD_DIR }}\n",
                    shell="{{ env.CUSTOM_SHELL }}",
                    dockerfile="{{ env.BUILD_DIR }}/Dockerfile",
                    context="{{ tt.project_root }}/{{ env.BUILD_DIR }}",
                )

                builtin_vars = {
                    "project_root": str(project_root),
                    "task_name": "test",
                }

                # Apply substitution
                substituted_runner = executor._substitute_builtin_in_runner(
                    runner, builtin_vars
                )

                # Verify substitution occurred
                self.assertEqual(
                    substituted_runner.preamble, "set -e\nexport BUILD_DIR=docker\n"
                )
                self.assertEqual(substituted_runner.shell, "/bin/bash")
                self.assertEqual(substituted_runner.dockerfile, "docker/Dockerfile")
                self.assertEqual(substituted_runner.context, f"{project_root}/docker")
        finally:
            del os.environ["BUILD_DIR"]
            del os.environ["CUSTOM_SHELL"]


class TestGetSessionDefaultRunner(unittest.TestCase):
    """
    Tests for get_session_default_runner() function.
    @athena: to-be-generated
    """

    @patch("platform.system")
    def test_returns_bash_on_unix(self, mock_system):
        """
        Test that get_session_default_runner returns bash runner on Unix platforms.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner()

            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")
            self.assertEqual(runner.args, ["-c"])
            self.assertEqual(runner.preamble, "")

    @patch("platform.system")
    def test_returns_bash_on_macos(self, mock_system):
        """
        Test that get_session_default_runner returns bash runner on macOS.
        @athena: to-be-generated
        """
        mock_system.return_value = "Darwin"

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner()

            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")
            self.assertEqual(runner.args, ["-c"])
            self.assertEqual(runner.preamble, "")

    @patch("platform.system")
    def test_returns_cmd_on_windows(self, mock_system):
        """
        Test that get_session_default_runner returns cmd runner on Windows.
        @athena: to-be-generated
        """
        mock_system.return_value = "Windows"

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner()

            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "cmd")
            self.assertEqual(runner.args, ["/c"])
            self.assertEqual(runner.preamble, "")

    @patch("platform.system")
    def test_returns_project_config_runner_when_found(self, mock_system):
        """
        Test that get_session_default_runner returns project config runner when available.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a temporary directory with a project config file
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_path = project_root / ".tasktree-config.yml"
            config_path.write_text(
                """
runners:
  default:
    shell: zsh
    preamble: set -e
"""
            )

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "zsh")
            self.assertEqual(runner.preamble, "set -e")

    @patch("platform.system")
    def test_falls_back_to_platform_default_when_no_config(self, mock_system):
        """
        Test that get_session_default_runner falls back to platform default when no config.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a temporary directory without a config file
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")
            self.assertEqual(runner.args, ["-c"])

    @patch("platform.system")
    def test_handles_config_parse_errors_gracefully(self, mock_system):
        """
        Test that get_session_default_runner falls back to platform default on parse errors.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a temporary directory with an invalid config file
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_path = project_root / ".tasktree-config.yml"
            config_path.write_text("invalid: yaml: content:")

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Should fall back to platform default on parse error
            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")
            self.assertEqual(runner.args, ["-c"])

    @patch("platform.system")
    def test_searches_parent_directories_for_config(self, mock_system):
        """
        Test that get_session_default_runner searches parent directories for config.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a nested directory structure with config in parent
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_path = project_root / ".tasktree-config.yml"
            config_path.write_text(
                """
runners:
  default:
    shell: fish
"""
            )

            # Create a subdirectory
            subdir = project_root / "subdir" / "nested"
            subdir.mkdir(parents=True)

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=subdir)

            # Should find config from parent directory
            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "fish")

    @patch("platform.system")
    @patch("tasktree.config.get_user_config_path")
    def test_returns_user_config_runner_when_found(self, mock_get_user_config, mock_system):
        """
        Test that get_session_default_runner returns user config runner when available.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a temporary directory with a user config file
        with tempfile.TemporaryDirectory() as tmpdir:
            user_config_path = Path(tmpdir) / "user-config.yml"
            user_config_path.write_text(
                """
runners:
  default:
    shell: zsh
    preamble: set -euo pipefail
"""
            )
            mock_get_user_config.return_value = user_config_path

            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "zsh")
            self.assertEqual(runner.preamble, "set -euo pipefail")

    @patch("platform.system")
    @patch("tasktree.config.get_user_config_path")
    def test_project_config_overrides_user_config(self, mock_get_user_config, mock_system):
        """
        Test that project config takes precedence over user config.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create user config
            user_config_path = Path(tmpdir) / "user-config.yml"
            user_config_path.write_text(
                """
runners:
  default:
    shell: zsh
"""
            )
            mock_get_user_config.return_value = user_config_path

            # Create project config
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            project_config_path = project_root / ".tasktree-config.yml"
            project_config_path.write_text(
                """
runners:
  default:
    shell: fish
"""
            )

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Project config should win
            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "fish")

    @patch("platform.system")
    @patch("tasktree.config.get_user_config_path")
    def test_user_config_overrides_platform_default(self, mock_get_user_config, mock_system):
        """
        Test that user config takes precedence over platform default.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create user config
            user_config_path = Path(tmpdir) / "user-config.yml"
            user_config_path.write_text(
                """
runners:
  default:
    shell: zsh
"""
            )
            mock_get_user_config.return_value = user_config_path

            # No project config
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # User config should win over platform default
            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "zsh")

    @patch("platform.system")
    @patch("tasktree.config.get_user_config_path")
    def test_handles_user_config_parse_errors_gracefully(
        self, mock_get_user_config, mock_system
    ):
        """
        Test that get_session_default_runner falls back when user config has parse errors.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid user config
            user_config_path = Path(tmpdir) / "user-config.yml"
            user_config_path.write_text("invalid: yaml: content:")
            mock_get_user_config.return_value = user_config_path

            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Should fall back to platform default
            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")

    @patch("platform.system")
    @patch("tasktree.config.get_machine_config_path")
    def test_returns_machine_config_runner_when_found(
        self, mock_get_machine_config, mock_system
    ):
        """
        Test that get_session_default_runner returns machine config runner when available.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a temporary directory with a machine config file
        with tempfile.TemporaryDirectory() as tmpdir:
            machine_config_path = Path(tmpdir) / "machine-config.yml"
            machine_config_path.write_text(
                """
runners:
  default:
    shell: fish
    preamble: set -eu
"""
            )
            mock_get_machine_config.return_value = machine_config_path

            project_root = Path(tmpdir) / "project"
            project_root.mkdir()
            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "fish")
            self.assertEqual(runner.preamble, "set -eu")

    @patch("platform.system")
    @patch("tasktree.config.get_machine_config_path")
    def test_machine_config_overrides_platform_default(
        self, mock_get_machine_config, mock_system
    ):
        """
        Test that machine config takes precedence over platform default.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create machine config
            machine_config_path = Path(tmpdir) / "machine-config.yml"
            machine_config_path.write_text(
                """
runners:
  default:
    shell: fish
"""
            )
            mock_get_machine_config.return_value = machine_config_path

            # No user or project config
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Machine config should win over platform default
            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "fish")

    @patch("platform.system")
    @patch("tasktree.config.get_user_config_path")
    @patch("tasktree.config.get_machine_config_path")
    def test_user_config_overrides_machine_config(
        self, mock_get_machine_config, mock_get_user_config, mock_system
    ):
        """
        Test that user config takes precedence over machine config.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create machine config
            machine_config_path = Path(tmpdir) / "machine-config.yml"
            machine_config_path.write_text(
                """
runners:
  default:
    shell: fish
"""
            )
            mock_get_machine_config.return_value = machine_config_path

            # Create user config
            user_config_path = Path(tmpdir) / "user-config.yml"
            user_config_path.write_text(
                """
runners:
  default:
    shell: zsh
"""
            )
            mock_get_user_config.return_value = user_config_path

            # No project config
            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # User config should win
            self.assertEqual(runner.name, "default")
            self.assertEqual(runner.shell, "zsh")

    @patch("platform.system")
    @patch("tasktree.config.get_machine_config_path")
    def test_handles_machine_config_permission_errors_gracefully(
        self, mock_get_machine_config, mock_system
    ):
        """
        Test that get_session_default_runner falls back when machine config has permission errors.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create machine config path (doesn't need to exist)
            machine_config_path = Path(tmpdir) / "machine-config.yml"
            mock_get_machine_config.return_value = machine_config_path

            # Mock exists() to return True, then parse_config_file to raise PermissionError
            with patch.object(Path, "exists", return_value=True), patch(
                "tasktree.executor.parse_config_file",
                side_effect=PermissionError("Permission denied"),
            ):
                project_root = Path(tmpdir) / "project"
                project_root.mkdir(exist_ok=True)

                state_manager = StateManager(project_root)
                recipe = Recipe(
                    tasks={},
                    project_root=project_root,
                    recipe_path=project_root / "tasktree.yaml",
                )
                executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
                runner = executor.get_session_default_runner(start_dir=project_root)

                # Should fall back to platform default
                self.assertEqual(runner.name, "__platform_default__")
                self.assertEqual(runner.shell, "bash")

    @patch("platform.system")
    @patch("tasktree.config.get_machine_config_path")
    def test_handles_empty_machine_config_file(
        self, mock_get_machine_config, mock_system
    ):
        """
        Test that get_session_default_runner handles empty machine config files gracefully.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty machine config
            machine_config_path = Path(tmpdir) / "machine-config.yml"
            machine_config_path.write_text("")  # Empty file
            mock_get_machine_config.return_value = machine_config_path

            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )
            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Empty config should be treated as no config, fall back to platform default
            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")

    @patch("platform.system")
    @patch("tasktree.config.get_machine_config_path")
    def test_handles_malformed_yaml_in_machine_config(
        self, mock_get_machine_config, mock_system
    ):
        """
        Test that get_session_default_runner handles malformed YAML in machine config gracefully.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create machine config with malformed YAML
            machine_config_path = Path(tmpdir) / "machine-config.yml"
            machine_config_path.write_text("invalid: yaml: content:")  # Malformed YAML
            mock_get_machine_config.return_value = machine_config_path

            project_root = Path(tmpdir) / "project"
            project_root.mkdir()

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            # Create a mock logger to capture log calls
            mock_logger = MagicMock()
            executor = Executor(recipe, state_manager, mock_logger, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Malformed YAML should log warning and fall back to platform default
            self.assertEqual(runner.name, "__platform_default__")
            self.assertEqual(runner.shell, "bash")

            # Verify warning was logged
            mock_logger.warn.assert_called()
            call_args = str(mock_logger.warn.call_args)
            self.assertIn("Failed to load machine config", call_args)

    @patch("platform.system")
    def test_logs_warning_when_config_parse_fails(self, mock_system):
        """
        Test that get_session_default_runner logs a warning when config parsing fails.
        @athena: to-be-generated
        """
        mock_system.return_value = "Linux"

        # Create a temporary directory with an invalid config file
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            config_path = project_root / ".tasktree-config.yml"
            config_path.write_text("invalid: yaml: content:")

            state_manager = StateManager(project_root)
            recipe = Recipe(
                tasks={},
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
            )

            # Create a mock logger to capture log calls
            mock_logger = MagicMock()
            executor = Executor(recipe, state_manager, mock_logger, make_process_runner)
            runner = executor.get_session_default_runner(start_dir=project_root)

            # Should fall back to platform default
            self.assertEqual(runner.name, "__platform_default__")

            # Should have logged a warning
            mock_logger.warn.assert_called_once()
            call_args = mock_logger.warn.call_args[0][0]
            self.assertIn("Failed to load project config", call_args)


class TestPlatformdirs(unittest.TestCase):
    """
    Test that platformdirs dependency is available.
    @athena: to-be-generated
    """

    def test_platformdirs_import(self):
        """
        Test that platformdirs can be imported successfully.
        @athena: to-be-generated
        """
        try:
            import platformdirs

            # Verify basic functions exist
            self.assertTrue(callable(platformdirs.user_config_dir))
            self.assertTrue(callable(platformdirs.site_config_dir))
        except ImportError as e:
            self.fail(f"platformdirs import failed: {e}")


if __name__ == "__main__":
    unittest.main()
