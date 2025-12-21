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


if __name__ == "__main__":
    unittest.main()
