"""Parse recipe YAML files and handle imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class CircularImportError(Exception):
    """Raised when a circular import is detected."""
    pass


@dataclass
class Environment:
    """Represents an execution environment configuration."""

    name: str
    shell: str
    args: list[str] = field(default_factory=list)
    preamble: str = ""

    def __post_init__(self):
        """Ensure args is always a list."""
        if isinstance(self.args, str):
            self.args = [self.args]


@dataclass
class Task:
    """Represents a task definition."""

    name: str
    cmd: str
    desc: str = ""
    deps: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    working_dir: str = ""
    args: list[str] = field(default_factory=list)
    source_file: str = ""  # Track which file defined this task
    env: str = ""  # Environment name to use for execution

    def __post_init__(self):
        """Ensure lists are always lists."""
        if isinstance(self.deps, str):
            self.deps = [self.deps]
        if isinstance(self.inputs, str):
            self.inputs = [self.inputs]
        if isinstance(self.outputs, str):
            self.outputs = [self.outputs]
        if isinstance(self.args, str):
            self.args = [self.args]


@dataclass
class Recipe:
    """Represents a parsed recipe file with all tasks."""

    tasks: dict[str, Task]
    project_root: Path
    environments: dict[str, Environment] = field(default_factory=dict)
    default_env: str = ""  # Name of default environment
    global_env_override: str = ""  # Global environment override (set via CLI --env)

    def get_task(self, name: str) -> Task | None:
        """Get task by name.

        Args:
            name: Task name (may be namespaced like 'build.compile')

        Returns:
            Task if found, None otherwise
        """
        return self.tasks.get(name)

    def task_names(self) -> list[str]:
        """Get all task names."""
        return list(self.tasks.keys())

    def get_environment(self, name: str) -> Environment | None:
        """Get environment by name.

        Args:
            name: Environment name

        Returns:
            Environment if found, None otherwise
        """
        return self.environments.get(name)


def find_recipe_file(start_dir: Path | None = None) -> Path | None:
    """Find recipe file (tasktree.yaml or tt.yaml) in current or parent directories.

    Args:
        start_dir: Directory to start searching from (defaults to cwd)

    Returns:
        Path to recipe file if found, None otherwise
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Search up the directory tree
    while True:
        for filename in ["tasktree.yaml", "tt.yaml"]:
            recipe_path = current / filename
            if recipe_path.exists():
                return recipe_path

        # Move to parent directory
        parent = current.parent
        if parent == current:
            # Reached root
            break
        current = parent

    return None


def _parse_file_with_env(
    file_path: Path,
    namespace: str | None,
    project_root: Path,
    import_stack: list[Path] | None = None,
) -> tuple[dict[str, Task], dict[str, Environment], str]:
    """Parse file and extract tasks and environments.

    Args:
        file_path: Path to YAML file
        namespace: Optional namespace prefix for tasks
        project_root: Root directory of the project
        import_stack: Stack of files being imported (for circular detection)

    Returns:
        Tuple of (tasks, environments, default_env_name)
    """
    # Parse tasks normally
    tasks = _parse_file(file_path, namespace, project_root, import_stack)

    # Load YAML again to extract environments (only from root file)
    environments: dict[str, Environment] = {}
    default_env = ""

    # Only parse environments from the root file (namespace is None)
    if namespace is None:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        if data and "environments" in data:
            env_data = data["environments"]
            if isinstance(env_data, dict):
                # Extract default environment name
                default_env = env_data.get("default", "")

                # Parse each environment definition
                for env_name, env_config in env_data.items():
                    if env_name == "default":
                        continue  # Skip the default key itself

                    if not isinstance(env_config, dict):
                        raise ValueError(
                            f"Environment '{env_name}' must be a dictionary"
                        )

                    # Parse environment configuration
                    shell = env_config.get("shell", "")
                    if not shell:
                        raise ValueError(
                            f"Environment '{env_name}' must specify 'shell'"
                        )

                    args = env_config.get("args", [])
                    preamble = env_config.get("preamble", "")

                    environments[env_name] = Environment(
                        name=env_name, shell=shell, args=args, preamble=preamble
                    )

    return tasks, environments, default_env


def parse_recipe(recipe_path: Path) -> Recipe:
    """Parse a recipe file and handle imports recursively.

    Args:
        recipe_path: Path to the main recipe file

    Returns:
        Recipe object with all tasks (including recursively imported tasks)

    Raises:
        FileNotFoundError: If recipe file doesn't exist
        CircularImportError: If circular imports are detected
        yaml.YAMLError: If YAML is invalid
        ValueError: If recipe structure is invalid
    """
    if not recipe_path.exists():
        raise FileNotFoundError(f"Recipe file not found: {recipe_path}")

    project_root = recipe_path.parent

    # Parse main file - it will recursively handle all imports
    tasks, environments, default_env = _parse_file_with_env(
        recipe_path, namespace=None, project_root=project_root
    )

    return Recipe(
        tasks=tasks,
        project_root=project_root,
        environments=environments,
        default_env=default_env,
    )


def _parse_file(
    file_path: Path,
    namespace: str | None,
    project_root: Path,
    import_stack: list[Path] | None = None,
) -> dict[str, Task]:
    """Parse a single YAML file and return tasks, recursively processing imports.

    Args:
        file_path: Path to YAML file
        namespace: Optional namespace prefix for tasks
        project_root: Root directory of the project
        import_stack: Stack of files being imported (for circular detection)

    Returns:
        Dictionary of task name to Task objects

    Raises:
        CircularImportError: If a circular import is detected
        FileNotFoundError: If an imported file doesn't exist
        ValueError: If task structure is invalid
    """
    # Initialize import stack if not provided
    if import_stack is None:
        import_stack = []

    # Detect circular imports
    if file_path in import_stack:
        chain = " → ".join(str(f.name) for f in import_stack + [file_path])
        raise CircularImportError(f"Circular import detected: {chain}")

    # Add current file to stack
    import_stack.append(file_path)

    # Load YAML
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}

    tasks: dict[str, Task] = {}
    file_dir = file_path.parent

    # Default working directory is the file's directory
    default_working_dir = str(file_dir.relative_to(project_root)) if file_dir != project_root else "."

    # Track local import namespaces for dependency rewriting
    local_import_namespaces: set[str] = set()

    # Process nested imports FIRST
    imports = data.get("import", [])
    if imports:
        for import_spec in imports:
            child_file = import_spec["file"]
            child_namespace = import_spec["as"]

            # Track this namespace as a local import
            local_import_namespaces.add(child_namespace)

            # Build full namespace chain
            full_namespace = f"{namespace}.{child_namespace}" if namespace else child_namespace

            # Resolve import path relative to current file's directory
            child_path = file_path.parent / child_file
            if not child_path.exists():
                raise FileNotFoundError(f"Import file not found: {child_path}")

            # Recursively process with namespace chain and import stack
            nested_tasks = _parse_file(
                child_path,
                full_namespace,
                project_root,
                import_stack.copy(),  # Pass copy to avoid shared mutation
            )

            tasks.update(nested_tasks)

    # Determine where tasks are defined
    # Tasks can be either at root level OR inside a "tasks:" key
    tasks_data = data.get("tasks", data) if "tasks" in data else data

    # Process local tasks
    for task_name, task_data in tasks_data.items():
        # Skip special sections (only relevant if tasks are at root level)
        if task_name in ("import", "environments", "tasks"):
            continue

        if not isinstance(task_data, dict):
            raise ValueError(f"Task '{task_name}' must be a dictionary")

        if "cmd" not in task_data:
            raise ValueError(f"Task '{task_name}' missing required 'cmd' field")

        # Apply namespace if provided
        full_name = f"{namespace}.{task_name}" if namespace else task_name

        # Set working directory
        working_dir = task_data.get("working_dir", default_working_dir)

        # Rewrite dependencies with namespace
        deps = task_data.get("deps", [])
        if isinstance(deps, str):
            deps = [deps]
        if namespace:
            # Rewrite dependencies: only prefix if it's a local reference
            # A dependency is local if:
            # 1. It has no dots (simple name like "init")
            # 2. It starts with a local import namespace (like "base.setup" when "base" is imported)
            rewritten_deps = []
            for dep in deps:
                if "." not in dep:
                    # Simple name - always prefix
                    rewritten_deps.append(f"{namespace}.{dep}")
                else:
                    # Check if it starts with a local import namespace
                    dep_root = dep.split(".", 1)[0]
                    if dep_root in local_import_namespaces:
                        # Local import reference - prefix it
                        rewritten_deps.append(f"{namespace}.{dep}")
                    else:
                        # External reference - keep as-is
                        rewritten_deps.append(dep)
            deps = rewritten_deps

        task = Task(
            name=full_name,
            cmd=task_data["cmd"],
            desc=task_data.get("desc", ""),
            deps=deps,
            inputs=task_data.get("inputs", []),
            outputs=task_data.get("outputs", []),
            working_dir=working_dir,
            args=task_data.get("args", []),
            source_file=str(file_path),
        )

        tasks[full_name] = task

    # Remove current file from stack
    import_stack.pop()

    return tasks


def parse_arg_spec(arg_spec: str) -> tuple[str, str, str | None]:
    """Parse argument specification.

    Format: name:type=default
    - name is required
    - type is optional (defaults to 'str')
    - default is optional

    Args:
        arg_spec: Argument specification string

    Returns:
        Tuple of (name, type, default)

    Examples:
        >>> parse_arg_spec("environment")
        ('environment', 'str', None)
        >>> parse_arg_spec("region=eu-west-1")
        ('region', 'str', 'eu-west-1')
        >>> parse_arg_spec("port:int=8080")
        ('port', 'int', '8080')
    """
    # Split on = to separate name:type from default
    if "=" in arg_spec:
        name_type, default = arg_spec.split("=", 1)
    else:
        name_type = arg_spec
        default = None

    # Split on : to separate name from type
    if ":" in name_type:
        name, arg_type = name_type.split(":", 1)
    else:
        name = name_type
        arg_type = "str"

    return name, arg_type, default
