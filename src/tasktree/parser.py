"""Parse recipe YAML files and handle imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


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


def parse_recipe(recipe_path: Path) -> Recipe:
    """Parse a recipe file and handle imports.

    Args:
        recipe_path: Path to the main recipe file

    Returns:
        Recipe object with all tasks

    Raises:
        FileNotFoundError: If recipe file doesn't exist
        yaml.YAMLError: If YAML is invalid
        ValueError: If recipe structure is invalid
    """
    if not recipe_path.exists():
        raise FileNotFoundError(f"Recipe file not found: {recipe_path}")

    with open(recipe_path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        data = {}

    project_root = recipe_path.parent
    tasks: dict[str, Task] = {}

    # Process imports first
    imports = data.get("import", [])
    if imports:
        for import_spec in imports:
            import_file = import_spec["file"]
            namespace = import_spec["as"]

            import_path = project_root / import_file
            if not import_path.exists():
                raise FileNotFoundError(f"Import file not found: {import_path}")

            # Parse imported file
            imported_tasks = _parse_file(import_path, namespace, project_root)
            tasks.update(imported_tasks)

    # Process local tasks
    local_tasks = _parse_file(recipe_path, None, project_root)
    tasks.update(local_tasks)

    return Recipe(tasks=tasks, project_root=project_root)


def _parse_file(
    file_path: Path, namespace: str | None, project_root: Path
) -> dict[str, Task]:
    """Parse a single YAML file and return tasks.

    Args:
        file_path: Path to YAML file
        namespace: Optional namespace prefix for tasks
        project_root: Root directory of the project

    Returns:
        Dictionary of task name to Task objects
    """
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    tasks: dict[str, Task] = {}
    file_dir = file_path.parent

    # Default working directory is the file's directory
    default_working_dir = str(file_dir.relative_to(project_root)) if file_dir != project_root else "."

    for task_name, task_data in data.items():
        # Skip import declarations
        if task_name == "import":
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
            # Rewrite internal dependencies to use namespace
            deps = [
                f"{namespace}.{dep}" if not "." in dep else dep
                for dep in deps
            ]

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
