"""Dependency resolution using topological sorting."""

from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any

from tasktree.hasher import hash_args
from tasktree.parser import Recipe, Task, DependencyInvocation, parse_dependency_spec


class CycleError(Exception):
    """Raised when a dependency cycle is detected."""

    pass


class TaskNotFoundError(Exception):
    """Raised when a task dependency doesn't exist."""

    pass


class TaskNode:
    """Represents a node in the dependency graph (task + arguments).

    Each node represents a unique invocation of a task with specific arguments.
    Tasks invoked with different arguments are considered different nodes.
    """

    def __init__(self, task_name: str, args: dict[str, Any] | None = None):
        self.task_name = task_name
        self.args = args or {}

    def __hash__(self):
        """Hash based on task name and sorted args."""
        if not self.args:
            return hash(self.task_name)
        args_hash = hash_args(self.args)
        return hash((self.task_name, args_hash))

    def __eq__(self, other):
        """Equality based on task name and args."""
        if not isinstance(other, TaskNode):
            return False
        return self.task_name == other.task_name and self.args == other.args

    def __repr__(self):
        if not self.args:
            return f"TaskNode({self.task_name})"
        args_str = ", ".join(f"{k}={v}" for k, v in sorted(self.args.items()))
        return f"TaskNode({self.task_name}, {{{args_str}}})"

    def __str__(self):
        if not self.args:
            return self.task_name
        args_str = ", ".join(f"{k}={v}" for k, v in sorted(self.args.items()))
        return f"{self.task_name}({args_str})"


def resolve_execution_order(
    recipe: Recipe,
    target_task: str,
    target_args: dict[str, Any] | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """Resolve execution order for a task and its dependencies.

    Args:
        recipe: Parsed recipe containing all tasks
        target_task: Name of the task to execute
        target_args: Arguments for the target task (optional)

    Returns:
        List of (task_name, args_dict) tuples in execution order (dependencies first)

    Raises:
        TaskNotFoundError: If target task or any dependency doesn't exist
        CycleError: If a dependency cycle is detected
    """
    if target_task not in recipe.tasks:
        raise TaskNotFoundError(f"Task not found: {target_task}")

    # Build dependency graph using TaskNode objects
    graph: dict[TaskNode, set[TaskNode]] = {}

    # Track seen nodes to detect duplicates
    seen_invocations: dict[tuple[str, str], TaskNode] = {}  # (task_name, args_hash) -> node

    def get_or_create_node(task_name: str, args: dict[str, Any] | None) -> TaskNode:
        """Get existing node or create new one for this invocation."""
        args_dict = args or {}
        args_hash = hash_args(args_dict) if args_dict else ""
        key = (task_name, args_hash)

        if key not in seen_invocations:
            seen_invocations[key] = TaskNode(task_name, args_dict)
        return seen_invocations[key]

    def build_graph(node: TaskNode) -> None:
        """Recursively build dependency graph."""
        if node in graph:
            # Already processed
            return

        task = recipe.tasks.get(node.task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {node.task_name}")

        # Parse and normalize dependencies
        dep_nodes = set()
        for dep_spec in task.deps:
            # Parse dependency specification
            dep_inv = parse_dependency_spec(dep_spec, recipe)

            # Create or get node for this dependency invocation
            dep_node = get_or_create_node(dep_inv.task_name, dep_inv.args)
            dep_nodes.add(dep_node)

        # Add task to graph with its dependency nodes
        graph[node] = dep_nodes

        # Recursively process dependencies
        for dep_node in dep_nodes:
            build_graph(dep_node)

    # Create root node for target task
    root_node = get_or_create_node(target_task, target_args)

    # Build graph starting from target task
    build_graph(root_node)

    # Use TopologicalSorter to resolve execution order
    try:
        sorter = TopologicalSorter(graph)
        ordered_nodes = list(sorter.static_order())

        # Convert TaskNode objects to (task_name, args_dict) tuples
        return [(node.task_name, node.args) for node in ordered_nodes]
    except ValueError as e:
        raise CycleError(f"Dependency cycle detected: {e}")


def get_implicit_inputs(recipe: Recipe, task: Task) -> list[str]:
    """Get implicit inputs for a task based on its dependencies.

    Tasks automatically inherit inputs from dependencies:
    1. All outputs from dependency tasks become implicit inputs
    2. All inputs from dependency tasks that don't declare outputs are inherited
    3. If task uses a Docker environment, Docker artifacts become implicit inputs:
       - Dockerfile
       - .dockerignore (if present)
       - Special markers for context directory and base image digests

    Args:
        recipe: Parsed recipe containing all tasks
        task: Task to get implicit inputs for

    Returns:
        List of glob patterns for implicit inputs, including Docker-specific markers
    """
    implicit_inputs = []

    # Inherit from dependencies
    for dep_spec in task.deps:
        # Parse dependency to get task name (ignore args for input inheritance)
        dep_inv = parse_dependency_spec(dep_spec, recipe)
        dep_task = recipe.tasks.get(dep_inv.task_name)
        if dep_task is None:
            continue

        # If dependency has outputs, inherit them
        if dep_task.outputs:
            implicit_inputs.extend(dep_task.outputs)
        # If dependency has no outputs, inherit its inputs
        elif dep_task.inputs:
            implicit_inputs.extend(dep_task.inputs)

    # Add Docker-specific implicit inputs if task uses Docker environment
    env_name = task.env or recipe.default_env
    if env_name:
        env = recipe.get_environment(env_name)
        if env and env.dockerfile:
            # Add Dockerfile as input
            implicit_inputs.append(env.dockerfile)

            # Add .dockerignore if it exists in context directory
            context_path = recipe.project_root / env.context
            dockerignore_path = context_path / ".dockerignore"
            if dockerignore_path.exists():
                relative_dockerignore = str(
                    dockerignore_path.relative_to(recipe.project_root)
                )
                implicit_inputs.append(relative_dockerignore)

            # Add special markers for context directory and digest tracking
            # These are tracked differently in state management (not file paths)
            # The executor will handle these specially
            implicit_inputs.append(f"_docker_context_{env.context}")
            implicit_inputs.append(f"_docker_dockerfile_{env.dockerfile}")

    return implicit_inputs


def build_dependency_tree(recipe: Recipe, target_task: str, target_args: dict[str, Any] | None = None) -> dict:
    """Build a tree structure representing dependencies for visualization.

    Note: This builds a true tree representation where shared dependencies may
    appear multiple times. Each dependency is shown in the context of its parent,
    allowing the full dependency path to be visible from any node.

    Args:
        recipe: Parsed recipe containing all tasks
        target_task: Name of the task to build tree for
        target_args: Arguments for the target task (optional)

    Returns:
        Nested dictionary representing the dependency tree
    """
    if target_task not in recipe.tasks:
        raise TaskNotFoundError(f"Task not found: {target_task}")

    current_path = set()  # Track current recursion path for cycle detection

    def build_tree(task_name: str, args: dict[str, Any] | None) -> dict:
        """Recursively build dependency tree."""
        task = recipe.tasks.get(task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {task_name}")

        # Create node identifier for cycle detection
        from tasktree.hasher import hash_args
        args_dict = args or {}
        node_id = (task_name, hash_args(args_dict) if args_dict else "")

        # Detect cycles in current recursion path
        if node_id in current_path:
            display_name = task_name if not args_dict else f"{task_name}({', '.join(f'{k}={v}' for k, v in sorted(args_dict.items()))})"
            return {"name": display_name, "deps": [], "cycle": True}

        current_path.add(node_id)

        # Parse dependencies
        dep_trees = []
        for dep_spec in task.deps:
            dep_inv = parse_dependency_spec(dep_spec, recipe)
            dep_tree = build_tree(dep_inv.task_name, dep_inv.args)
            dep_trees.append(dep_tree)

        # Create display name (include args if present)
        display_name = task_name
        if args_dict:
            args_str = ", ".join(f"{k}={v}" for k, v in sorted(args_dict.items()))
            display_name = f"{task_name}({args_str})"

        tree = {
            "name": display_name,
            "deps": dep_trees,
        }

        current_path.remove(node_id)

        return tree

    return build_tree(target_task, target_args)
