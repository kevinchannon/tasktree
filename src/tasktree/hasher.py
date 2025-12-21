"""Hashing logic for tasks and arguments."""

import hashlib
import json
from typing import Any


def hash_task(cmd: str, outputs: list[str], working_dir: str, args: list[str]) -> str:
    """Compute task definition hash.

    The hash includes:
    - cmd: The command to execute
    - outputs: Declared output files
    - working_dir: Execution directory
    - args: Parameter definitions (names and types)

    The hash excludes:
    - deps: Only affects scheduling order
    - inputs: Tracked separately via timestamps
    - desc: Documentation only

    Args:
        cmd: Command to execute
        outputs: List of output glob patterns
        working_dir: Working directory for execution
        args: List of argument definitions

    Returns:
        8-character hex hash string
    """
    # Create a stable representation
    data = {
        "cmd": cmd,
        "outputs": sorted(outputs),  # Sort for stability
        "working_dir": working_dir,
        "args": sorted(args),  # Sort for stability
    }

    # Serialize to JSON with sorted keys for deterministic hashing
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))

    # Compute hash and truncate to 8 characters
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def hash_args(args_dict: dict[str, Any]) -> str:
    """Compute hash of task arguments.

    Args:
        args_dict: Dictionary of argument names to values

    Returns:
        8-character hex hash string
    """
    # Serialize arguments to JSON with sorted keys for deterministic hashing
    serialized = json.dumps(args_dict, sort_keys=True, separators=(",", ":"))

    # Compute hash and truncate to 8 characters
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def make_cache_key(task_hash: str, args_hash: str | None = None) -> str:
    """Create cache key for task execution.

    Args:
        task_hash: Task definition hash
        args_hash: Optional arguments hash

    Returns:
        Cache key string (task_hash or task_hash__args_hash)
    """
    if args_hash:
        return f"{task_hash}__{args_hash}"
    return task_hash
