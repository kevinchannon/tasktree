"""Dependency resolution using topological sorting."""

from graphlib import TopologicalSorter
from pathlib import Path
from typing import Any

from tasktree.hasher import hash_args
from tasktree.parser import (
    Recipe,
    Task,
    DependencyInvocation,
    parse_dependency_spec,
    parse_arg_spec,
)
from tasktree.substitution import substitute_dependency_args


def _get_exported_arg_names(task: Task) -> set[str]:
    """Extract names of exported arguments from a task.

    Exported arguments are identified by the '$' prefix in their definition.

    Args:
        task: Task to extract exported arg names from

    Returns:
        Set of exported argument names (without the '$' prefix)

    Example:
        Task with args: ["$server", "port"]
        Returns: {"server"}
    """
    if not task.args:
        return set()

    exported = set()
    for arg_spec in task.args:
        if isinstance(arg_spec, str):
            # Simple string format: "$argname" or "argname"
            if arg_spec.startswith("$"):
                exported.add(arg_spec[1:])  # Remove '$' prefix
        elif isinstance(arg_spec, dict):
            # Dictionary format: {"$argname": {...}} or {"argname": {...}}
            for arg_name in arg_spec.keys():
                if arg_name.startswith("$"):
                    exported.add(arg_name[1:])  # Remove '$' prefix

    return exported


def resolve_dependency_invocation(
    dep_spec: str | dict[str, Any],
    parent_task_name: str,
    parent_args: dict[str, Any],
    parent_exported_args: set[str],
    recipe: Recipe
) -> DependencyInvocation:
    """Parse dependency specification and substitute parent argument templates.

    This function handles template substitution in dependency arguments. It:
    1. Checks if dependency arguments contain {{ arg.* }} templates
    2. Substitutes templates using parent task's arguments
    3. Delegates to parse_dependency_spec for type conversion and validation

    Args:
        dep_spec: Dependency specification (str or dict with task name and args)
        parent_task_name: Name of the parent task (for error messages)
        parent_args: Parent task's argument values (for template substitution)
        parent_exported_args: Set of parent's exported argument names
        recipe: Recipe containing task definitions

    Returns:
        DependencyInvocation with typed, validated arguments

    Raises:
        ValueError: If template substitution fails, argument validation fails,
                   or dependency task doesn't exist

    Examples:
        Simple string (no templates):
        >>> resolve_dependency_invocation("build", "test", {}, set(), recipe)
        DependencyInvocation("build", None)

        Literal arguments (no templates):
        >>> resolve_dependency_invocation({"build": ["debug"]}, "test", {}, set(), recipe)
        DependencyInvocation("build", {"mode": "debug"})

        Template substitution:
        >>> resolve_dependency_invocation(
        ...     {"build": ["{{ arg.env }}"]},
        ...     "test",
        ...     {"env": "production"},
        ...     set(),
        ...     recipe
        ... )
        DependencyInvocation("build", {"mode": "production"})
    """
    # Simple string case - no args to substitute
    if isinstance(dep_spec, str):
        return parse_dependency_spec(dep_spec, recipe)

    # Dictionary case: {"task_name": args_spec}
    if not isinstance(dep_spec, dict) or len(dep_spec) != 1:
        # Invalid format, let parse_dependency_spec handle the error
        return parse_dependency_spec(dep_spec, recipe)

    task_name, arg_spec = next(iter(dep_spec.items()))

    # Check if any argument values contain templates
    has_templates = False
    if isinstance(arg_spec, list):
        # Positional args: check each value
        for val in arg_spec:
            if isinstance(val, str) and "{{ arg." in val:
                has_templates = True
                break
    elif isinstance(arg_spec, dict):
        # Named args: check each value
        for val in arg_spec.values():
            if isinstance(val, str) and "{{ arg." in val:
                has_templates = True
                break

    # If no templates, use existing parser (fast path for backward compatibility)
    if not has_templates:
        return parse_dependency_spec(dep_spec, recipe)

    # Template substitution path
    # Substitute {{ arg.* }} in argument values
    substituted_arg_spec: list[Any] | dict[str, Any]

    if isinstance(arg_spec, list):
        # Positional args: substitute each value that's a string
        substituted_arg_spec = []
        for val in arg_spec:
            if isinstance(val, str):
                substituted_val = substitute_dependency_args(
                    val, parent_task_name, parent_args, parent_exported_args
                )
                substituted_arg_spec.append(substituted_val)
            else:
                # Non-string values (bool, int, etc.) pass through unchanged
                substituted_arg_spec.append(val)
    elif isinstance(arg_spec, dict):
        # Named args: substitute each string value
        substituted_arg_spec = {}
        for arg_name, val in arg_spec.items():
            if isinstance(val, str):
                substituted_val = substitute_dependency_args(
                    val, parent_task_name, parent_args, parent_exported_args
                )
                substituted_arg_spec[arg_name] = substituted_val
            else:
                # Non-string values pass through unchanged
                substituted_arg_spec[arg_name] = val
    else:
        # Invalid format, let parse_dependency_spec handle it
        return parse_dependency_spec(dep_spec, recipe)

    # Create new dep_spec with substituted values and parse it
    substituted_dep_spec = {task_name: substituted_arg_spec}
    return parse_dependency_spec(substituted_dep_spec, recipe)


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
        self.args = args  # Keep None as None

    def __hash__(self):
        """Hash based on task name and sorted args."""
        # Treat None and {} as equivalent for hashing
        if not self.args:
            return hash(self.task_name)
        args_hash = hash_args(self.args)
        return hash((self.task_name, args_hash))

    def __eq__(self, other):
        """Equality based on task name and args."""
        if not isinstance(other, TaskNode):
            return False
        # Treat None and {} as equivalent
        self_args = self.args if self.args else {}
        other_args = other.args if other.args else {}
        return self.task_name == other.task_name and self_args == other_args

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
        args_hash = hash_args(args) if args else ""
        key = (task_name, args_hash)

        if key not in seen_invocations:
            seen_invocations[key] = TaskNode(task_name, args)
        return seen_invocations[key]

    def build_graph(node: TaskNode) -> None:
        """Recursively build dependency graph with template substitution."""
        if node in graph:
            # Already processed
            return

        task = recipe.tasks.get(node.task_name)
        if task is None:
            raise TaskNotFoundError(f"Task not found: {node.task_name}")

        # Get parent task's exported argument names
        parent_exported_args = _get_exported_arg_names(task)

        # Parse and normalize dependencies with template substitution
        dep_nodes = set()
        for dep_spec in task.deps:
            # Resolve dependency specification with parent context
            # This handles template substitution if {{ arg.* }} is present
            dep_inv = resolve_dependency_invocation(
                dep_spec,
                parent_task_name=node.task_name,
                parent_args=node.args or {},
                parent_exported_args=parent_exported_args,
                recipe=recipe
            )

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


def resolve_dependency_output_references(
    recipe: Recipe,
    ordered_tasks: list[tuple[str, dict[str, Any]]],
) -> None:
    """Resolve {{ dep.<task>.outputs.<name> }} references in topological order.

    This function walks through tasks in dependency order (dependencies first) and
    resolves any references to dependency outputs in task fields. Templates are
    resolved in place, modifying the Task objects in the recipe.

    Args:
        recipe: Recipe containing task definitions
        ordered_tasks: List of (task_name, args) tuples in topological order

    Raises:
        ValueError: If template references cannot be resolved (missing task,
                   missing output, task not in dependencies, etc.)

    Example:
        Given tasks in topological order: [('build', {}), ('deploy', {})]
        If deploy.cmd contains "{{ dep.build.outputs.bundle }}", it will be
        resolved to the actual output path from the build task.
    """
    from tasktree.substitution import substitute_dependency_outputs

    # Track which tasks have been resolved (for validation)
    resolved_tasks = {}

    for task_name, task_args in ordered_tasks:
        task = recipe.tasks.get(task_name)
        if task is None:
            continue  # Skip if task doesn't exist (shouldn't happen)

        # Get list of dependency task names for this task
        dep_task_names = []
        for dep_spec in task.deps:
            # Handle both string and dict dependency specs
            if isinstance(dep_spec, str):
                dep_task_names.append(dep_spec)
            elif isinstance(dep_spec, dict):
                # Dict spec: {"task_name": [args]}
                dep_task_names.append(list(dep_spec.keys())[0])

        # Resolve output references in command
        if task.cmd:
            task.cmd = substitute_dependency_outputs(
                task.cmd,
                task_name,
                dep_task_names,
                resolved_tasks,
            )

        # Resolve output references in working_dir
        if task.working_dir:
            task.working_dir = substitute_dependency_outputs(
                task.working_dir,
                task_name,
                dep_task_names,
                resolved_tasks,
            )

        # Resolve output references in outputs
        resolved_outputs = []
        for output in task.outputs:
            if isinstance(output, str):
                resolved_outputs.append(
                    substitute_dependency_outputs(
                        output,
                        task_name,
                        dep_task_names,
                        resolved_tasks,
                    )
                )
            elif isinstance(output, dict):
                # Named output: resolve the path value
                resolved_dict = {}
                for name, path in output.items():
                    resolved_dict[name] = substitute_dependency_outputs(
                        path,
                        task_name,
                        dep_task_names,
                        resolved_tasks,
                    )
                resolved_outputs.append(resolved_dict)
        task.outputs = resolved_outputs

        # Rebuild output maps after resolution
        task.__post_init__()

        # Resolve output references in argument defaults
        if task.args:
            for arg_spec in task.args:
                if isinstance(arg_spec, dict):
                    # Get arg name and details
                    for arg_name, arg_details in arg_spec.items():
                        if isinstance(arg_details, dict) and "default" in arg_details:
                            if isinstance(arg_details["default"], str):
                                arg_details["default"] = substitute_dependency_outputs(
                                    arg_details["default"],
                                    task_name,
                                    dep_task_names,
                                    resolved_tasks,
                                )

        # Mark this task as resolved for future references
        resolved_tasks[task_name] = task


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
            # Extract paths from both named and anonymous outputs
            for output in dep_task.outputs:
                if isinstance(output, str):
                    # Anonymous output: just the path
                    implicit_inputs.append(output)
                elif isinstance(output, dict):
                    # Named output: extract path values
                    implicit_inputs.extend(output.values())
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
