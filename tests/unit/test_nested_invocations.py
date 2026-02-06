"""Tests for nested task invocations (Phase 1: State Management)."""

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


if __name__ == "__main__":
    unittest.main()
