"""Task Tree - A task automation tool with intelligent incremental execution."""

__version__ = "0.1.0"

from tasktree.executor import Executor, ExecutionError, TaskStatus
from tasktree.graph import (
    CycleError,
    TaskNotFoundError,
    build_dependency_tree,
    get_implicit_inputs,
    resolve_execution_order,
)
from tasktree.hasher import hash_args, hash_task, make_cache_key
from tasktree.parser import Recipe, Task, find_recipe_file, parse_arg_spec, parse_recipe
from tasktree.state import StateManager, TaskState

__all__ = [
    "__version__",
    "Executor",
    "ExecutionError",
    "TaskStatus",
    "CycleError",
    "TaskNotFoundError",
    "build_dependency_tree",
    "get_implicit_inputs",
    "resolve_execution_order",
    "hash_args",
    "hash_task",
    "make_cache_key",
    "Recipe",
    "Task",
    "find_recipe_file",
    "parse_arg_spec",
    "parse_recipe",
    "StateManager",
    "TaskState",
]
