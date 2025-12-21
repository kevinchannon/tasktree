"""Dependency resolution using topological sorting."""

from graphlib import TopologicalSorter

from tasktree.parser import Recipe, Task


class CycleError(Exception):
    """Raised when a dependency cycle is detected."""

    pass


class TaskNotFoundError(Exception):
    """Raised when a task dependency doesn't exist."""

    pass


def resolve_execution_order(recipe: Recipe, target_task: str) -> list[str]:
    """Resolve execution order for a task and its dependencies.

    Args:
        recipe: Parsed recipe containing all tasks
        target_task: Name of the task to execute

    Returns:
        List of task names in execution order (dependencies first)

    Raises:
        TaskNotFoundError: If target task or any dependency doesn't exist
        CycleError: If a dependency cycle is detected
    """
    if target_task not in recipe.tasks:
        raise TaskNotFoundError(f"Task not found: {target_task}")

    # Build dependency graph
    graph: dict[str, set[str]] = {}

    def build_graph(task_name: str) -> None:
        """Recursively build dependency graph."""
        if task_name in graph:
            # Already processed
            return

        task = recipe.tasks.get(task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {task_name}")

        # Add task to graph with its dependencies
        graph[task_name] = set(task.deps)

        # Recursively process dependencies
        for dep in task.deps:
            build_graph(dep)

    # Build graph starting from target task
    build_graph(target_task)

    # Use TopologicalSorter to resolve execution order
    try:
        sorter = TopologicalSorter(graph)
        return list(sorter.static_order())
    except ValueError as e:
        raise CycleError(f"Dependency cycle detected: {e}")


def get_implicit_inputs(recipe: Recipe, task: Task) -> list[str]:
    """Get implicit inputs for a task based on its dependencies.

    Tasks automatically inherit inputs from dependencies:
    1. All outputs from dependency tasks become implicit inputs
    2. All inputs from dependency tasks that don't declare outputs are inherited

    Args:
        recipe: Parsed recipe containing all tasks
        task: Task to get implicit inputs for

    Returns:
        List of glob patterns for implicit inputs
    """
    implicit_inputs = []

    for dep_name in task.deps:
        dep_task = recipe.tasks.get(dep_name)
        if dep_task is None:
            continue

        # If dependency has outputs, inherit them
        if dep_task.outputs:
            implicit_inputs.extend(dep_task.outputs)
        # If dependency has no outputs, inherit its inputs
        elif dep_task.inputs:
            implicit_inputs.extend(dep_task.inputs)

    return implicit_inputs


def build_dependency_tree(recipe: Recipe, target_task: str) -> dict:
    """Build a tree structure representing dependencies for visualization.

    Args:
        recipe: Parsed recipe containing all tasks
        target_task: Name of the task to build tree for

    Returns:
        Nested dictionary representing the dependency tree
    """
    if target_task not in recipe.tasks:
        raise TaskNotFoundError(f"Task not found: {target_task}")

    visited = set()

    def build_tree(task_name: str) -> dict:
        """Recursively build dependency tree."""
        task = recipe.tasks.get(task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {task_name}")

        # Prevent infinite recursion on cycles
        if task_name in visited:
            return {"name": task_name, "deps": [], "cycle": True}

        visited.add(task_name)

        tree = {
            "name": task_name,
            "deps": [build_tree(dep) for dep in task.deps],
        }

        visited.remove(task_name)

        return tree

    return build_tree(target_task)
