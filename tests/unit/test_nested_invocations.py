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


class TestStateMtimeOptimization(unittest.TestCase):
    """Tests for state file mtime-based reload optimization."""

    def test_state_not_reloaded_if_mtime_unchanged(self):
        """
        Test that state is not reloaded if modification time hasn't changed.
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

            # Get initial mtime
            initial_mtime = state_manager.get_mtime()
            self.assertIsNotNone(initial_mtime)

            # Wait a tiny bit to ensure mtime would be different if file was modified
            time.sleep(0.01)

            # Get mtime again without modifying file
            current_mtime = state_manager.get_mtime()

            # Verify mtime is unchanged
            self.assertEqual(initial_mtime, current_mtime)

    def test_state_mtime_changes_when_file_modified(self):
        """
        Test that mtime changes when state file is actually modified.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create initial state
            state_manager = StateManager(project_root)
            state_manager.load()
            state_manager.set("task_a", TaskState(last_run=100.0, input_state={}))
            state_manager.save()

            # Get initial mtime
            initial_mtime = state_manager.get_mtime()

            # Wait to ensure filesystem mtime granularity
            time.sleep(0.01)

            # Modify state file (simulate nested call)
            state_manager2 = StateManager(project_root)
            state_manager2.load()
            state_manager2.set("task_b", TaskState(last_run=200.0, input_state={}))
            state_manager2.save()

            # Get new mtime
            new_mtime = state_manager.get_mtime()

            # Verify mtime changed
            self.assertNotEqual(initial_mtime, new_mtime)

    def test_state_mtime_none_when_file_not_exists(self):
        """
        Test that get_mtime returns None when state file doesn't exist.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # State file doesn't exist yet
            mtime = state_manager.get_mtime()
            self.assertIsNone(mtime)

    def test_executor_skips_reload_when_mtime_unchanged(self):
        """
        Test that Executor skips state reload when mtime hasn't changed.
        This verifies the optimization in _run_task.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create minimal recipe
            recipe = Recipe(
                project_root=project_root,
                recipe_dir=project_root,
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
            executor = Executor(
                recipe=recipe,
                state=state_manager,
                logger=logger_stub,
                force=False,
                only=False,
            )

            # Mock the state.load() method to track calls
            original_load = state_manager.load
            load_call_count = {"count": 0}

            def mock_load():
                load_call_count["count"] += 1
                original_load()

            state_manager.load = mock_load

            # Execute task
            process_runner = make_process_runner(
                task_name="simple",
                use_pty=False,
                capture_stdout=True,
                capture_stderr=True,
                logger=logger_stub,
            )

            executor._run_task(recipe.tasks["simple"], {}, process_runner)

            # State should be loaded once initially (before we started tracking)
            # but NOT reloaded after execution since mtime unchanged
            # The mock started tracking after initial load in executor
            # So we expect 0 additional loads
            self.assertEqual(load_call_count["count"], 0)


if __name__ == "__main__":
    unittest.main()
