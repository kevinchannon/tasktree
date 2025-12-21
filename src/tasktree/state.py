"""State file management and pruning."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TaskState:
    """State for a single task execution."""

    last_run: float
    input_state: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_run": self.last_run,
            "input_state": self.input_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskState":
        """Create from dictionary loaded from JSON."""
        return cls(
            last_run=data["last_run"],
            input_state=data.get("input_state", {}),
        )


class StateManager:
    """Manages the .tasktree-state file."""

    STATE_FILE = ".tasktree-state"

    def __init__(self, project_root: Path):
        """Initialize state manager.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = project_root
        self.state_path = project_root / self.STATE_FILE
        self._state: dict[str, TaskState] = {}
        self._loaded = False

    def load(self) -> None:
        """Load state from file if it exists."""
        if self.state_path.exists():
            try:
                with open(self.state_path, "r") as f:
                    data = json.load(f)
                    self._state = {
                        key: TaskState.from_dict(value)
                        for key, value in data.items()
                    }
            except (json.JSONDecodeError, KeyError) as e:
                # If state file is corrupted, start fresh
                self._state = {}
        self._loaded = True

    def save(self) -> None:
        """Save state to file."""
        data = {key: value.to_dict() for key, value in self._state.items()}
        with open(self.state_path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, cache_key: str) -> TaskState | None:
        """Get state for a task.

        Args:
            cache_key: Cache key (task_hash or task_hash__args_hash)

        Returns:
            TaskState if found, None otherwise
        """
        if not self._loaded:
            self.load()
        return self._state.get(cache_key)

    def set(self, cache_key: str, state: TaskState) -> None:
        """Set state for a task.

        Args:
            cache_key: Cache key (task_hash or task_hash__args_hash)
            state: TaskState to store
        """
        if not self._loaded:
            self.load()
        self._state[cache_key] = state

    def prune(self, valid_task_hashes: set[str]) -> None:
        """Remove state entries for tasks that no longer exist.

        Args:
            valid_task_hashes: Set of valid task hashes from current recipe
        """
        if not self._loaded:
            self.load()

        # Find keys to remove
        keys_to_remove = []
        for cache_key in self._state.keys():
            # Extract task hash (before __ if present)
            task_hash = cache_key.split("__")[0]
            if task_hash not in valid_task_hashes:
                keys_to_remove.append(cache_key)

        # Remove stale entries
        for key in keys_to_remove:
            del self._state[key]

    def clear(self) -> None:
        """Clear all state (useful for testing)."""
        self._state = {}
        self._loaded = True
