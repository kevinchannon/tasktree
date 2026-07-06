"""Tests for state module."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.state import StateManager, TaskState


class TestTaskState(unittest.TestCase):
    """
    """

    def test_to_dict(self):
        """
        Test converting TaskState to dictionary.
        """
        state = TaskState(last_run=1234567890.0, input_state={"file.txt": 1234567880.0})
        data = state.to_dict()
        self.assertEqual(data["last_run"], 1234567890.0)
        self.assertEqual(data["input_state"], {"file.txt": 1234567880.0})

    def test_from_dict(self):
        """
        Test creating TaskState from dictionary.
        """
        data = {"last_run": 1234567890.0, "input_state": {"file.txt": 1234567880.0}}
        state = TaskState.from_dict(data)
        self.assertEqual(state.last_run, 1234567890.0)
        self.assertEqual(state.input_state, {"file.txt": 1234567880.0})

    def test_task_name_round_trips(self):
        """
        Test that task_name survives to_dict/from_dict.
        """
        state = TaskState(last_run=1234567890.0, task_name="build.compile")
        data = state.to_dict()
        self.assertEqual(data["task_name"], "build.compile")
        self.assertEqual(TaskState.from_dict(data).task_name, "build.compile")

    def test_from_dict_without_task_name_defaults_to_empty(self):
        """
        Test that legacy entries (no task_name) load with an empty name.
        """
        data = {"last_run": 1234567890.0}
        self.assertEqual(TaskState.from_dict(data).task_name, "")


class TestStateManager(unittest.TestCase):
    """
    """

    def test_save_and_load(self):
        """
        Test saving and loading state.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Set some state
            state = TaskState(
                last_run=1234567890.0, input_state={"file.txt": 1234567880.0}
            )
            state_manager.set("abc12345", state)
            state_manager.save()

            # Create new state manager and load
            new_state_manager = StateManager(project_root)
            new_state_manager.load()
            loaded_state = new_state_manager.get("abc12345")

            self.assertIsNotNone(loaded_state)
            self.assertEqual(loaded_state.last_run, 1234567890.0)
            self.assertEqual(loaded_state.input_state, {"file.txt": 1234567880.0})

    def test_prune(self):
        """
        Test pruning stale state entries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Set state for multiple tasks
            state_manager.set("abc12345", TaskState(last_run=1234567890.0))
            state_manager.set("abc12345__def67890", TaskState(last_run=1234567890.0))
            state_manager.set("xyz99999", TaskState(last_run=1234567890.0))

            # Prune - keep only abc12345
            state_manager.prune({"abc12345"})

            # Check that only abc12345 entries remain
            self.assertIsNotNone(state_manager.get("abc12345"))
            self.assertIsNotNone(
                state_manager.get("abc12345__def67890")
            )  # Should keep parameterized versions
            self.assertIsNone(state_manager.get("xyz99999"))  # Should be pruned

    def test_prune_name_aware(self):
        """
        Test the name-aware pruning rule.
        """
        with TemporaryDirectory() as tmpdir:
            state_manager = StateManager(Path(tmpdir))

            state_manager.set(
                "aaa11111", TaskState(last_run=1.0, task_name="deleted-task")
            )
            state_manager.set(
                "bbb22222", TaskState(last_run=1.0, task_name="sleeping-task")
            )
            state_manager.set(
                "ccc33333", TaskState(last_run=1.0, task_name="invoked-task")
            )
            state_manager.set(
                "ddd44444", TaskState(last_run=1.0, task_name="invoked-task")
            )
            state_manager.set("eee55555", TaskState(last_run=1.0))  # legacy, no name

            state_manager.prune(
                {"ccc33333"},
                defined_task_names={"sleeping-task", "invoked-task"},
                reachable_task_names={"invoked-task"},
            )

            # Task gone from the recipe: pruned
            self.assertIsNone(state_manager.get("aaa11111"))
            # Defined but not part of this run: kept despite unknown hash
            self.assertIsNotNone(state_manager.get("bbb22222"))
            # Part of this run with a current hash: kept
            self.assertIsNotNone(state_manager.get("ccc33333"))
            # Part of this run with a stale hash: pruned
            self.assertIsNone(state_manager.get("ddd44444"))
            # Legacy nameless entry: hash-only rule
            self.assertIsNone(state_manager.get("eee55555"))

    def test_clear(self):
        """
        Test clearing all state.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Set some state
            state_manager.set("abc12345", TaskState(last_run=1234567890.0))
            state_manager.clear()

            # Check that state is cleared
            self.assertIsNone(state_manager.get("abc12345"))


class TestStateErrors(unittest.TestCase):
    """
    Tests for state error conditions.
    """

    def test_state_corrupted_json(self):
        """
        Test StateManager handles corrupted JSON gracefully.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_file = project_root / ".tasktree-state"

            # Create a corrupted JSON file
            state_file.write_text("{ invalid json content }")

            # StateManager should handle this gracefully and start with empty state
            state_manager = StateManager(project_root)
            state_manager.load()

            # Should have empty state (corrupted file ignored)
            self.assertIsNone(state_manager.get("any_key"))

            # Should be able to save new state
            state_manager.set("new_key", TaskState(last_run=1234567890.0))
            state_manager.save()

            # Should be able to load the new state
            state_manager2 = StateManager(project_root)
            state_manager2.load()
            self.assertIsNotNone(state_manager2.get("new_key"))


if __name__ == "__main__":
    unittest.main()
