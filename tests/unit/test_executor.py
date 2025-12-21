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


if __name__ == "__main__":
    unittest.main()
