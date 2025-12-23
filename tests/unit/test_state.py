"""Tests for state module."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.state import StateManager, TaskState


class TestTaskState(unittest.TestCase):
    def test_to_dict(self):
        """Test converting TaskState to dictionary."""
        state = TaskState(
            last_run=1234567890.0, input_state={"file.txt": 1234567880.0}
        )
        data = state.to_dict()
        self.assertEqual(data["last_run"], 1234567890.0)
        self.assertEqual(data["input_state"], {"file.txt": 1234567880.0})

    def test_from_dict(self):
        """Test creating TaskState from dictionary."""
        data = {"last_run": 1234567890.0, "input_state": {"file.txt": 1234567880.0}}
        state = TaskState.from_dict(data)
        self.assertEqual(state.last_run, 1234567890.0)
        self.assertEqual(state.input_state, {"file.txt": 1234567880.0})


class TestStateManager(unittest.TestCase):
    def test_save_and_load(self):
        """Test saving and loading state."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Set some state
            state = TaskState(last_run=1234567890.0, input_state={"file.txt": 1234567880.0})
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
        """Test pruning stale state entries."""
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

    def test_clear(self):
        """Test clearing all state."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            state_manager = StateManager(project_root)

            # Set some state
            state_manager.set("abc12345", TaskState(last_run=1234567890.0))
            state_manager.clear()

            # Check that state is cleared
            self.assertIsNone(state_manager.get("abc12345"))


class TestStateErrors(unittest.TestCase):
    """Tests for state error conditions."""

    def test_state_corrupted_json(self):
        """Test StateManager handles corrupted JSON gracefully."""
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
