"""Tests for nested task invocations (Phase 1: State Management)."""

import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from helpers.logging import logger_stub
from tasktree.executor import Executor
from tasktree.parser import Recipe, Task
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager, TaskState


class TestStateManagementCore(unittest.TestCase):
    """Tests for core state reload and upsert behavior."""

    def test_state_reload_after_execution(self):
        """
        Test that state can be reloaded after task execution.
        Simulates nested call modifying state during parent execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Initial state setup
            state_manager.load()
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Simulate parent loading state
            state_manager_parent = StateManager(project_root)
            state_manager_parent.load()

            # Verify parent has initial state
            self.assertEqual(state_manager_parent.get("task_a").last_run, 100.0)

            # Simulate nested call modifying state (writes task_b)
            state_manager_child = StateManager(project_root)
            state_manager_child.load()
            state_manager_child.set("task_b", TaskState(last_run=200.0, input_state={}))
            state_manager_child.save()

            # Parent reloads state
            state_manager_parent.load()

            # Verify parent now sees both tasks
            self.assertIsNotNone(state_manager_parent.get("task_a"))
            self.assertIsNotNone(state_manager_parent.get("task_b"))
            self.assertEqual(state_manager_parent.get("task_b").last_run, 200.0)

    def test_state_upsert_preserves_other_entries(self):
        """
        Test that upserting one task's state preserves other entries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Create state with 3 tasks
            state_manager.load()
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.set("task_b", TaskState(last_run=200.0, input_state={}))
            state_manager.set("task_c", TaskState(last_run=300.0, input_state={}))
            state_manager.save()

            # Reload and upsert task_b
            state_manager.load()
            state_manager.set("task_b", TaskState(last_run=250.0, input_state={}))
            state_manager.save()

            # Reload and verify
            state_manager_verify = StateManager(project_root)
            state_manager_verify.load()
            self.assertEqual(state_manager_verify.get("task_a").last_run, 100.0)
            self.assertEqual(state_manager_verify.get("task_b").last_run, 250.0)
            self.assertEqual(state_manager_verify.get("task_c").last_run, 300.0)

    def test_multiple_state_loads_idempotent(self):
        """
        Test that loading state multiple times produces identical results.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Create initial state
            state_manager.load()
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Load 3 times
            state_manager.load()
            first_load = state_manager.get("task_a").last_run

            state_manager.load()
            second_load = state_manager.get("task_a").last_run

            state_manager.load()
            third_load = state_manager.get("task_a").last_run

            # All loads should produce same result
            self.assertEqual(first_load, 100.0)
            self.assertEqual(second_load, 100.0)
            self.assertEqual(third_load, 100.0)

    def test_empty_state_file_reload(self):
        """
        Test that reloading works correctly with initially empty state.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Start with empty state (no file exists)
            state_manager.load()
            self.assertIsNone(state_manager.get("task_a"))

            # Add entry and save
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Reload from disk
            state_manager.load()
            self.assertEqual(state_manager.get("task_a").last_run, 100.0)

    def test_concurrent_state_modification_simulation(self):
        """
        Test that parent can correctly handle child process state writes.
        Simulates the full nested invocation pattern.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Parent loads state
            parent_state = StateManager(project_root)
            parent_state.load()
            parent_state.set("parent", TaskState(last_run=100.0, input_state={}))

            # Simulate child process writing state (before parent saves)
            child_state = StateManager(project_root)
            child_state.load()
            child_state.set("child", TaskState(last_run=200.0, input_state={}))
            child_state.save()

            # Parent reloads before saving (this is the key behavior)
            parent_state.load()
            parent_state.set("parent", TaskState(last_run=150.0, input_state={}))
            parent_state.save()

            # Verify final state has both entries
            verify_state = StateManager(project_root)
            verify_state.load()
            self.assertEqual(verify_state.get("parent").last_run, 150.0)
            self.assertEqual(verify_state.get("child").last_run, 200.0)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases in nested invocations."""

    def test_overlapping_outputs(self):
        """
        Test that overlapping outputs between parent and child are handled.
        Parent's final state should reflect actual filesystem state.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            output_file = project_root / "output.txt"

            # Create initial output
            output_file.write_text("initial")
            initial_mtime = output_file.stat().st_mtime

            # Sleep to ensure distinct timestamp
            time.sleep(0.01)

            # Simulate child modifying output
            output_file.write_text("child")
            child_mtime = output_file.stat().st_mtime

            # Sleep to ensure distinct timestamp
            time.sleep(0.01)

            # Simulate parent modifying output after child
            output_file.write_text("parent")
            parent_mtime = output_file.stat().st_mtime

            # Parent's state should reflect final filesystem state
            self.assertNotEqual(initial_mtime, parent_mtime)
            self.assertGreater(parent_mtime, child_mtime)
            self.assertEqual(output_file.read_text(), "parent")

    def test_nested_call_to_already_run_task(self):
        """
        Test that nested call can skip task if already run (incrementality).
        Simulates checking if task needs to run based on existing state.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Task B already ran and has state
            state_manager.load()
            state_manager.set("task_b", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Task A loads state (would call tt B)
            state_manager_a = StateManager(project_root)
            state_manager_a.load()

            # Verify task B's state exists (would allow skip decision)
            self.assertIsNotNone(state_manager_a.get("task_b"))
            self.assertEqual(state_manager_a.get("task_b").last_run, 100.0)

    def test_empty_command_only_nested_call(self):
        """
        Test task with cmd that only contains nested tt call.
        Parent state should still be created.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Simulate child running
            state_manager.load()
            state_manager.set("child", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Parent reloads and adds its own state
            state_manager.load()
            state_manager.set("parent", TaskState(last_run=200.0, input_state={}))
            state_manager.save()

            # Verify both exist
            verify = StateManager(project_root)
            verify.load()
            self.assertIsNotNone(verify.get("parent"))
            self.assertIsNotNone(verify.get("child"))

    def test_state_file_missing_during_nested_call(self):
        """
        Test handling when state file is deleted between parent load and reload.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_path = project_root / ".tasktree-state"

            # Parent loads state (empty)
            parent_state = StateManager(project_root)
            parent_state.load()

            # Delete state file (simulates corruption or deletion)
            if state_path.exists():
                state_path.unlink()

            # Child creates new state file
            child_state = StateManager(project_root)
            child_state.load()
            child_state.set("child", TaskState(last_run=100.0, input_state={}))
            child_state.save()

            # Parent reloads (file now exists)
            parent_state.load()
            parent_state.set("parent", TaskState(last_run=200.0, input_state={}))
            parent_state.save()

            # Verify final state has both
            verify = StateManager(project_root)
            verify.load()
            self.assertIsNotNone(verify.get("parent"))
            self.assertIsNotNone(verify.get("child"))

    def test_malformed_state_during_nested_call(self):
        """
        Test that malformed state is handled gracefully (fallback to empty).
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_path = project_root / ".tasktree-state"

            # Create malformed state file
            state_path.write_text("{invalid json")

            # State manager should handle gracefully
            state_manager = StateManager(project_root)
            state_manager.load()  # Should not raise, should start with empty state

            # Should be able to write valid state
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Verify recovery
            verify = StateManager(project_root)
            verify.load()
            self.assertEqual(verify.get("task_a").last_run, 100.0)

    def test_nested_call_no_output_always_runs(self):
        """
        Test that task with no outputs always runs (state tracking only).
        State should still be updated to track last run.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # First run
            state_manager.load()
            state_manager.set("no_output", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Second run (would run again because no outputs)
            state_manager.load()
            state_manager.set("no_output", TaskState(last_run=200.0, input_state={}))
            state_manager.save()

            # Verify state was updated
            verify = StateManager(project_root)
            verify.load()
            self.assertEqual(verify.get("no_output").last_run, 200.0)

    def test_parent_no_output_child_has_output(self):
        """
        Test parent with no outputs calling child with outputs.
        Child should benefit from incrementality, parent always runs.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # First run: both tasks run
            first_run = StateManager(project_root)
            first_run.load()
            first_run.set("parent", TaskState(last_run=100.0, input_state={}))
            first_run.set("child", TaskState(last_run=100.0, input_state={"out.txt": 100.0}))
            first_run.save()

            # Second run: parent would run (no outputs), child might skip
            second_run = StateManager(project_root)
            second_run.load()
            # Parent always updates (no outputs means always runs)
            second_run.set("parent", TaskState(last_run=200.0, input_state={}))
            # Child state unchanged (would skip if outputs fresh)
            second_run.save()

            # Verify parent updated, child preserved
            verify = StateManager(project_root)
            verify.load()
            self.assertEqual(verify.get("parent").last_run, 200.0)
            self.assertEqual(verify.get("child").last_run, 100.0)

    def test_multiple_sequential_state_updates(self):
        """
        Test multiple nested calls updating state sequentially.
        Each update should be preserved in final state.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Initial state
            state_manager.load()

            # Sequential updates (simulating multiple nested calls)
            state_manager.set("child1", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            state_manager.load()
            state_manager.set("child2", TaskState(last_run=200.0, input_state={}))
            state_manager.save()

            state_manager.load()
            state_manager.set("child3", TaskState(last_run=300.0, input_state={}))
            state_manager.save()

            state_manager.load()
            state_manager.set("parent", TaskState(last_run=400.0, input_state={}))
            state_manager.save()

            # Verify all entries exist
            verify = StateManager(project_root)
            verify.load()
            self.assertEqual(verify.get("child1").last_run, 100.0)
            self.assertEqual(verify.get("child2").last_run, 200.0)
            self.assertEqual(verify.get("child3").last_run, 300.0)
            self.assertEqual(verify.get("parent").last_run, 400.0)

    def test_state_preservation_across_multiple_reloads(self):
        """
        Test that state entries are preserved across multiple load/save cycles.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Cycle 1: Create initial state
            state1 = StateManager(project_root)
            state1.load()
            state1.set("task1", TaskState(last_run=100.0, input_state={}))
            state1.save()

            # Cycle 2: Add another task
            state2 = StateManager(project_root)
            state2.load()
            self.assertIsNotNone(state2.get("task1"))  # Previous entry preserved
            state2.set("task2", TaskState(last_run=200.0, input_state={}))
            state2.save()

            # Cycle 3: Add third task
            state3 = StateManager(project_root)
            state3.load()
            self.assertIsNotNone(state3.get("task1"))  # First entry still preserved
            self.assertIsNotNone(state3.get("task2"))  # Second entry still preserved
            state3.set("task3", TaskState(last_run=300.0, input_state={}))
            state3.save()

            # Final verification
            verify = StateManager(project_root)
            verify.load()
            self.assertEqual(verify.get("task1").last_run, 100.0)
            self.assertEqual(verify.get("task2").last_run, 200.0)
            self.assertEqual(verify.get("task3").last_run, 300.0)


class TestStateHashOptimization(unittest.TestCase):
    """Tests for state file hash-based reload optimization."""

    def test_state_not_reloaded_if_hash_unchanged(self):
        """
        Test that state is not reloaded if file hash hasn't changed.
        This is the optimization to avoid unnecessary disk I/O when no nested calls occurred.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_file = project_root / ".tasktree-state"

            # Create initial state
            state_manager = StateManager(project_root)
            state_manager.load()
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Get initial hash
            initial_hash = state_manager.get_hash()
            self.assertIsNotNone(initial_hash)

            # Get hash again without modifying file contents
            current_hash = state_manager.get_hash()

            # Verify hash is unchanged
            self.assertEqual(initial_hash, current_hash)

    def test_state_hash_changes_when_file_modified(self):
        """
        Test that hash changes when state file contents are actually modified.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create initial state
            state_manager = StateManager(project_root)
            state_manager.load()
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Get initial hash
            initial_hash = state_manager.get_hash()

            # Modify state file contents (simulate nested call)
            state_manager2 = StateManager(project_root)
            state_manager2.load()
            state_manager2.set("task_b", TaskState(last_run=200.0, input_state={}))
            state_manager2.save()

            # Get new hash
            new_hash = state_manager.get_hash()

            # Verify hash changed
            self.assertNotEqual(initial_hash, new_hash)

    def test_state_hash_none_when_file_not_exists(self):
        """
        Test that get_hash returns None when state file doesn't exist.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # State file doesn't exist yet
            hash_value = state_manager.get_hash()
            self.assertIsNone(hash_value)

    def test_executor_skips_reload_when_hash_unchanged(self):
        """
        Test that Executor skips state reload when file hash hasn't changed.
        This verifies the optimization in _run_task.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create minimal recipe
            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "simple": Task(
                        name="simple",
                        desc="Simple task",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in=None,
                        args=[],
                        private=False,
                    )
                },
                runners={},
                variables={},
            )

            state_manager = StateManager(project_root)
            # Load state initially so set() won't trigger a load
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock the state.load() method to track calls AFTER initial load
            original_load = state_manager.load
            load_call_count = {"count": 0}

            def mock_load():
                load_call_count["count"] += 1
                original_load()

            state_manager.load = mock_load

            # Execute task
            process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

            executor._run_task(recipe.tasks["simple"], {}, process_runner)

            # State should be loaded once initially (before we started tracking)
            # but NOT reloaded after execution since hash unchanged
            # The mock started tracking after initial load in executor
            # So we expect 0 additional loads
            self.assertEqual(load_call_count["count"], 0)


class TestDockerEnvironmentSupport(unittest.TestCase):
    """Tests for Phase 2: Docker environment support for nested invocations."""

    def test_state_manager_uses_env_var_when_set(self):
        """
        Test that TT_STATE_FILE_PATH overrides default state file location.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            custom_state_path = "/workspace/.tasktree-state"

            with patch.dict("os.environ", {
                "TT_STATE_FILE_PATH": custom_state_path,
                "TT_CONTAINERIZED_RUNNER": "test-runner"
            }):
                state_manager = StateManager(project_root)
                self.assertEqual(str(state_manager.state_path), custom_state_path)
                self.assertEqual(state_manager.project_root, Path("/workspace"))

    def test_state_manager_default_path_when_no_env(self):
        """
        Test that default state file path is used when TT_STATE_FILE_PATH not set.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch.dict("os.environ", {}, clear=True):
                state_manager = StateManager(project_root)
                expected_path = project_root / ".tasktree-state"
                self.assertEqual(state_manager.state_path, expected_path)
                self.assertEqual(state_manager.project_root, project_root)

    def test_state_manager_error_on_state_path_without_runner(self):
        """
        Test that error is raised when TT_STATE_FILE_PATH is set but TT_CONTAINERIZED_RUNNER is not.
        This indicates a configuration error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            with patch.dict("os.environ", {"TT_STATE_FILE_PATH": "/workspace/.tasktree-state"}):
                with self.assertRaises(ValueError) as context:
                    StateManager(project_root)
                self.assertIn("TT_STATE_FILE_PATH is set but TT_CONTAINERIZED_RUNNER is not", str(context.exception))

    def test_same_docker_runner_uses_shell_execution(self):
        """
        Test that when inside a Docker container with matching runner, shell execution is used.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a Docker runner
            from tasktree.parser import Runner
            test_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="set -e",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "test": Task(
                        name="test",
                        desc="Test task",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="build",  # Same as current container
                        args=[],
                        private=False,
                    )
                },
                runners={"build": test_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock environment to simulate being inside Docker container
            with patch.dict("os.environ", {"TT_CONTAINERIZED_RUNNER": "build"}):
                # Mock _run_command_as_script to verify it's called (not Docker execution)
                with patch.object(executor, "_run_command_as_script") as mock_script:
                    with patch.object(executor, "_run_task_in_docker") as mock_docker:
                        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                        executor._run_task(recipe.tasks["test"], {}, process_runner)

                        # Verify shell execution was used, not Docker
                        mock_script.assert_called_once()
                        mock_docker.assert_not_called()

    def test_different_docker_runner_raises_error(self):
        """
        Test that switching to a different Docker runner raises an error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from tasktree.parser import Runner
            build_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile.build",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            test_runner = Runner(
                name="test",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile.test",  # Different dockerfile
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "child": Task(
                        name="child",
                        desc="Child task",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="test",  # Different Docker runner
                        args=[],
                        private=False,
                    )
                },
                runners={"build": build_runner, "test": test_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock environment to simulate being inside build container
            with patch.dict("os.environ", {"TT_CONTAINERIZED_RUNNER": "build"}):
                from tasktree.executor import ExecutionError
                with self.assertRaises(ExecutionError) as context:
                    process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                    executor._run_task(recipe.tasks["child"], {}, process_runner)

                self.assertIn("requires containerized runner 'test'", str(context.exception))
                self.assertIn("currently executing inside runner 'build'", str(context.exception))

    def test_shell_runner_switch_allowed_in_container(self):
        """
        Test that switching to a shell-only runner is allowed within a container.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from tasktree.parser import Runner
            docker_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            shell_runner = Runner(
                name="lint",
                default=False,
                shell="/bin/sh",
                preamble="set -e",
                dockerfile=None,  # Shell-only runner
                context=None,
                volumes=None,
                ports=None,
                env_vars=None,
                build_args=None,
                image=None,
                working_dir=None,
                args=None,
                extra_args=None,
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "lint": Task(
                        name="lint",
                        desc="Lint task",
                        cmd="echo 'lint'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="lint",  # Shell-only runner
                        args=[],
                        private=False,
                    )
                },
                runners={"build": docker_runner, "lint": shell_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock environment to simulate being inside Docker container
            with patch.dict("os.environ", {"TT_CONTAINERIZED_RUNNER": "build"}):
                # This should NOT raise an error (shell-only runner is allowed)
                with patch.object(executor, "_run_command_as_script") as mock_script:
                    process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                    executor._run_task(recipe.tasks["lint"], {}, process_runner)

                    # Verify shell execution was used
                    mock_script.assert_called_once()

    def test_no_runner_in_container_uses_shell(self):
        """
        Test that task with no runner specification executes in current container.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from tasktree.parser import Runner
            docker_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "no_runner": Task(
                        name="no_runner",
                        desc="Task without runner",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in=None,  # No runner specified
                        args=[],
                        private=False,
                    )
                },
                runners={"build": docker_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock environment to simulate being inside Docker container
            with patch.dict("os.environ", {"TT_CONTAINERIZED_RUNNER": "build"}):
                with patch.object(executor, "_run_command_as_script") as mock_script:
                    with patch.object(executor, "_run_task_in_docker") as mock_docker:
                        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                        executor._run_task(recipe.tasks["no_runner"], {}, process_runner)

                        # Verify shell execution was used
                        mock_script.assert_called_once()
                        mock_docker.assert_not_called()

    def test_local_to_docker_launches_container(self):
        """
        Test that local execution launches Docker container normally.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from tasktree.parser import Runner
            docker_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "docker_task": Task(
                        name="docker_task",
                        desc="Docker task",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="build",
                        args=[],
                        private=False,
                    )
                },
                runners={"build": docker_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # No TT_CONTAINERIZED_RUNNER env var (local execution)
            with patch.dict("os.environ", {}, clear=True):
                with patch.object(executor, "_run_task_in_docker") as mock_docker:
                    with patch.object(executor, "_run_command_as_script") as mock_script:
                        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                        executor._run_task(recipe.tasks["docker_task"], {}, process_runner)

                        # Verify Docker execution was used
                        mock_docker.assert_called_once()
                        mock_script.assert_not_called()

    def test_docker_env_vars_include_tt_vars(self):
        """
        Test that TT_CONTAINERIZED_RUNNER and TT_STATE_FILE_PATH are added to docker_env_vars.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from tasktree.parser import Runner
            docker_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "test": Task(
                        name="test",
                        desc="Test",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="build",
                        args=[],
                        private=False,
                    )
                },
                runners={"build": docker_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock docker_manager.run_in_container to capture env vars
            captured_env = {}
            def mock_run_in_container(env, **kwargs):
                captured_env.update(env.env_vars or {})

            with patch.object(executor.docker_manager, "run_in_container", side_effect=mock_run_in_container):
                process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                executor._run_task(recipe.tasks["test"], {}, process_runner)

            # Verify TT_* env vars were added
            self.assertEqual(captured_env.get("TT_CONTAINERIZED_RUNNER"), "build")
            self.assertEqual(captured_env.get("TT_STATE_FILE_PATH"), "/workspace/.tasktree-state")

    def test_state_file_mounted_as_volume(self):
        """
        Test that state file is mounted as a volume in Docker containers.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_file = project_root / ".tasktree-state"
            state_file.touch()  # Create state file

            from tasktree.parser import Runner
            docker_runner = Runner(
                name="build",
                default=False,
                shell="/bin/bash",
                preamble="",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "test": Task(
                        name="test",
                        desc="Test",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="build",
                        args=[],
                        private=False,
                    )
                },
                runners={"build": docker_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock docker_manager.run_in_container to capture volumes
            captured_volumes = []
            def mock_run_in_container(env, **kwargs):
                captured_volumes.extend(env.volumes or [])

            with patch.object(executor.docker_manager, "run_in_container", side_effect=mock_run_in_container):
                process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                executor._run_task(recipe.tasks["test"], {}, process_runner)

            # Verify state file was mounted
            state_mount = f"{state_file.absolute()}:/workspace/.tasktree-state"
            self.assertIn(state_mount, captured_volumes)

    def test_nested_call_uses_runner_shell_preamble(self):
        """
        Test that nested call in matching container uses runner's shell/preamble.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            from tasktree.parser import Runner
            docker_runner = Runner(
                name="build",
                default=False,
                shell="/bin/zsh",
                preamble="set -euo pipefail",
                dockerfile="Dockerfile",
                context=".",
                volumes=[],
                ports=[],
                env_vars={},
                build_args={},
                image=None,
                working_dir=None,
                args=[],
                extra_args=[],
            )

            recipe = Recipe(
                project_root=project_root,
                recipe_path=project_root / "tasktree.yaml",
                tasks={
                    "test": Task(
                        name="test",
                        desc="Test",
                        cmd="echo 'test'",
                        deps=[],
                        inputs=[],
                        outputs=[],
                        working_dir=".",
                        run_in="build",
                        args=[],
                        private=False,
                    )
                },
                runners={"build": docker_runner},
                variables={},
            )

            state_manager = StateManager(project_root)
            state_manager.load()

            executor = Executor(recipe, state_manager, logger_stub, make_process_runner)

            # Mock environment to simulate being inside container
            with patch.dict("os.environ", {"TT_CONTAINERIZED_RUNNER": "build"}):
                # Mock _run_command_as_script to capture shell/preamble
                captured_args = {}
                def mock_run_script(cmd, working_dir, task_name, shell, preamble, *args, **kwargs):
                    captured_args["shell"] = shell
                    captured_args["preamble"] = preamble

                with patch.object(executor, "_run_command_as_script", side_effect=mock_run_script):
                    process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
                    executor._run_task(recipe.tasks["test"], {}, process_runner)

                # Verify runner's shell and preamble were used
                self.assertEqual(captured_args["shell"], "/bin/zsh")
                self.assertEqual(captured_args["preamble"], "set -euo pipefail")


if __name__ == "__main__":
    unittest.main()
