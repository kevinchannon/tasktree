"""State file management and pruning."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Set


@dataclass
class TaskState:
    """
    State for a single task execution.
    @athena: b08a937b7f2f
    """

    last_run: float
    input_state: dict[str, float | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.
        @athena: 5f42efc35e77
        """
        return {
            "last_run": self.last_run,
            "input_state": self.input_state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskState":
        """
        Create from dictionary loaded from JSON.
        @athena: d9237db7e7e7
        """
        return cls(
            last_run=data["last_run"],
            input_state=data.get("input_state", {}),
        )


class StateManager:
    """
    Manages the .tasktree-state file.
    @athena: 3dd3447bb53b
    """

    STATE_FILE = ".tasktree-state"

    def __init__(self, project_root: Path):
        """
        Initialize state manager.

        Args:
        project_root: Root directory of the project
        @athena: a0afbd8ae591
        """
        # Check for containerized state file path first
        state_file_path_env = os.environ.get("TT_STATE_FILE_PATH")
        containerized_runner = os.environ.get("TT_CONTAINERIZED_RUNNER")

        # Validation: TT_STATE_FILE_PATH requires TT_CONTAINERIZED_RUNNER
        if state_file_path_env and not containerized_runner:
            raise ValueError(
                "TT_STATE_FILE_PATH is set but TT_CONTAINERIZED_RUNNER is not. "
                "This indicates a configuration error in the Docker container setup."
            )

        if state_file_path_env:
            # Use explicit state file path from environment
            self.state_path = Path(state_file_path_env)
            self.project_root = self.state_path.parent
        else:
            # Use default: co-located with recipe in project_root
            self.project_root = project_root
            self.state_path = project_root / self.STATE_FILE

        self._state: dict[str, TaskState] = {}
        self._loaded = False

    def load(self) -> None:
        """
        Load state from file if it exists.
        @athena: e0cf9097c590
        """
        if self.state_path.exists():
            try:
                with open(self.state_path, "r") as f:
                    data = json.load(f)
                    self._state = {
                        key: TaskState.from_dict(value) for key, value in data.items()
                    }
            except (json.JSONDecodeError, KeyError):
                # If state file is corrupted, start fresh
                self._state = {}
        self._loaded = True

    def save(self) -> None:
        """
        Save state to file.
        @athena: 11e4a9761e4d
        """
        data = {key: value.to_dict() for key, value in self._state.items()}
        with open(self.state_path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, cache_key: str) -> TaskState | None:
        """
        Get state for a task.

        Args:
        cache_key: Cache key (task_hash or task_hash__args_hash)

        Returns:
        TaskState if found, None otherwise
        @athena: fe5b27e855eb
        """
        if not self._loaded:
            self.load()
        return self._state.get(cache_key)

    def set(self, cache_key: str, state: TaskState) -> None:
        """
        Set state for a task.

        Args:
        cache_key: Cache key (task_hash or task_hash__args_hash)
        state: TaskState to store
        @athena: 244f16ea0ebc
        """
        if not self._loaded:
            self.load()
        self._state[cache_key] = state

    def prune(self, valid_task_hashes: Set[str]) -> None:
        """
        Remove state entries for tasks that no longer exist.

        Args:
        valid_task_hashes: Set of valid task hashes from current recipe
        @athena: 2717c6c244d3
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
        """
        Clear all state (useful for testing).
        @athena: 3a92e36d9f83
        """
        self._state = {}
        self._loaded = True

    def get_hash(self) -> str | None:
        """
        Get the hash of the state file contents.

        Returns:
        SHA256 hash of file contents, or None if file doesn't exist
        @athena: tbd
        """
        if not self.state_path.exists():
            return None

        with open(self.state_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
