"""Parse recipe YAML files and handle imports."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import yaml


class CircularImportError(Exception):
    """Raised when a circular import is detected."""
    pass


@dataclass
class Environment:
    """Represents an execution environment configuration.

    Can be either a shell environment or a Docker environment:
    - Shell environment: has 'shell' field, executes directly on host
    - Docker environment: has 'dockerfile' field, executes in container
    """

    name: str
    shell: str = ""  # Path to shell (required for shell envs, optional for Docker)
    args: list[str] = field(default_factory=list)
    preamble: str = ""
    # Docker-specific fields (presence of dockerfile indicates Docker environment)
    dockerfile: str = ""  # Path to Dockerfile
    context: str = ""  # Path to build context directory
    volumes: list[str] = field(default_factory=list)  # Volume mounts
    ports: list[str] = field(default_factory=list)  # Port mappings
    env_vars: dict[str, str] = field(default_factory=dict)  # Environment variables
    working_dir: str = ""  # Working directory (container or host)
    extra_args: List[str] = field(default_factory=list) # Any extra arguments to pass to docker
    run_as_root: bool = False  # If True, skip user mapping (run as root in container)

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
    variables: dict[str, str] = field(default_factory=dict)  # Global variables (resolved at parse time)

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
    """Find recipe file in current or parent directories.

    Looks for recipe files matching these patterns (in order of preference):
    - tasktree.yaml
    - tasktree.yml
    - tt.yaml
    - *.tasks

    If multiple recipe files are found in the same directory, raises ValueError
    with instructions to use --tasks option.

    Args:
        start_dir: Directory to start searching from (defaults to cwd)

    Returns:
        Path to recipe file if found, None otherwise

    Raises:
        ValueError: If multiple recipe files found in the same directory
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Search up the directory tree
    while True:
        candidates = []

        # Check for exact filenames first
        for filename in ["tasktree.yaml", "tasktree.yml", "tt.yaml"]:
            recipe_path = current / filename
            if recipe_path.exists():
                candidates.append(recipe_path)

        # Check for *.tasks files
        for tasks_file in current.glob("*.tasks"):
            if tasks_file.is_file():
                candidates.append(tasks_file)

        if len(candidates) > 1:
            # Multiple recipe files found - ambiguous
            filenames = [c.name for c in candidates]
            raise ValueError(
                f"Multiple recipe files found in {current}:\n"
                f"  {', '.join(filenames)}\n\n"
                f"Please specify which file to use with --tasks (-T):\n"
                f"  tt --tasks {filenames[0]} <task-name>"
            )
        elif len(candidates) == 1:
            return candidates[0]

        # Move to parent directory
        parent = current.parent
        if parent == current:
            # Reached root
            break
        current = parent

    return None


def _validate_variable_name(name: str) -> None:
    """Validate that a variable name is a valid identifier.

    Args:
        name: Variable name to validate

    Raises:
        ValueError: If name is not a valid identifier
    """
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(
            f"Variable name '{name}' is invalid. Names must start with "
            f"letter/underscore and contain only alphanumerics and underscores."
        )


def _infer_variable_type(value: Any) -> str:
    """Infer type name from Python value.

    Args:
        value: Python value from YAML

    Returns:
        Type name string (str, int, float, bool)

    Raises:
        ValueError: If value type is not supported
    """
    type_map = {
        str: "str",
        int: "int",
        float: "float",
        bool: "bool"
    }
    python_type = type(value)
    if python_type not in type_map:
        raise ValueError(
            f"Variable has unsupported type '{python_type.__name__}'. "
            f"Supported types: str, int, float, bool, path, datetime, ip, ipv4, ipv6, email, hostname"
        )
    return type_map[python_type]


def _is_env_variable_reference(value: Any) -> bool:
    """Check if value is an environment variable reference.

    Args:
        value: Raw value from YAML

    Returns:
        True if value is { env: VAR_NAME } dict
    """
    return isinstance(value, dict) and "env" in value


def _validate_env_variable_reference(var_name: str, value: dict) -> str:
    """Validate and extract environment variable name from reference.

    Args:
        var_name: Name of the variable being defined
        value: Dict that should be { env: ENV_VAR_NAME }

    Returns:
        Environment variable name

    Raises:
        ValueError: If reference is invalid
    """
    # Validate dict structure
    if len(value) != 1:
        extra_keys = [k for k in value.keys() if k != "env"]
        raise ValueError(
            f"Invalid environment variable reference in variable '{var_name}'.\n"
            f"Expected: {{ env: VARIABLE_NAME }}\n"
            f"Found extra keys: {', '.join(extra_keys)}"
        )

    env_var_name = value["env"]

    # Validate env var name is provided
    if not env_var_name or not isinstance(env_var_name, str):
        raise ValueError(
            f"Invalid environment variable reference in variable '{var_name}'.\n"
            f"Expected: {{ env: VARIABLE_NAME }}\n"
            f"Found: {{ env: {env_var_name!r} }}"
        )

    # Validate env var name format (allow both uppercase and mixed case for flexibility)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', env_var_name):
        raise ValueError(
            f"Invalid environment variable name '{env_var_name}' in variable '{var_name}'.\n"
            f"Environment variable names must start with a letter or underscore,\n"
            f"and contain only alphanumerics and underscores."
        )

    return env_var_name


def _resolve_env_variable(var_name: str, env_var_name: str) -> str:
    """Resolve environment variable value.

    Args:
        var_name: Name of the variable being defined
        env_var_name: Name of environment variable to read

    Returns:
        Environment variable value as string

    Raises:
        ValueError: If environment variable is not set
    """
    value = os.environ.get(env_var_name)

    if value is None:
        raise ValueError(
            f"Environment variable '{env_var_name}' (referenced by variable '{var_name}') is not set.\n\n"
            f"Hint: Set it before running tt:\n"
            f"  {env_var_name}=value tt task\n\n"
            f"Or export it in your shell:\n"
            f"  export {env_var_name}=value\n"
            f"  tt task"
        )

    return value


def _is_file_read_reference(value: Any) -> bool:
    """Check if value is a file read reference.

    Args:
        value: Raw value from YAML

    Returns:
        True if value is { read: filepath } dict
    """
    return isinstance(value, dict) and "read" in value


def _validate_file_read_reference(var_name: str, value: dict) -> str:
    """Validate and extract filepath from file read reference.

    Args:
        var_name: Name of the variable being defined
        value: Dict that should be { read: filepath }

    Returns:
        Filepath string

    Raises:
        ValueError: If reference is invalid
    """
    # Validate dict structure (only "read" key allowed)
    if len(value) != 1:
        extra_keys = [k for k in value.keys() if k != "read"]
        raise ValueError(
            f"Invalid file read reference in variable '{var_name}'.\n"
            f"Expected: {{ read: filepath }}\n"
            f"Found extra keys: {', '.join(extra_keys)}"
        )

    filepath = value["read"]

    # Validate filepath is provided and is a string
    if not filepath or not isinstance(filepath, str):
        raise ValueError(
            f"Invalid file read reference in variable '{var_name}'.\n"
            f"Expected: {{ read: filepath }}\n"
            f"Found: {{ read: {filepath!r} }}\n\n"
            f"Filepath must be a non-empty string."
        )

    return filepath


def _resolve_file_path(filepath: str, recipe_file_path: Path) -> Path:
    """Resolve file path relative to recipe file location.

    Handles three path types:
    1. Tilde paths (~): Expand to user home directory
    2. Absolute paths: Use as-is
    3. Relative paths: Resolve relative to recipe file's directory

    Args:
        filepath: Path string from YAML (may be relative, absolute, or tilde)
        recipe_file_path: Path to the recipe file containing the variable

    Returns:
        Resolved absolute Path object
    """
    # Expand tilde to home directory
    if filepath.startswith("~"):
        return Path(os.path.expanduser(filepath))

    # Convert to Path for is_absolute check
    path_obj = Path(filepath)

    # Absolute paths used as-is
    if path_obj.is_absolute():
        return path_obj

    # Relative paths resolved from recipe file's directory
    return recipe_file_path.parent / filepath


def _resolve_file_variable(var_name: str, filepath: str, resolved_path: Path) -> str:
    """Read file contents for variable value.

    Args:
        var_name: Name of the variable being defined
        filepath: Original filepath string (for error messages)
        resolved_path: Resolved absolute path to the file

    Returns:
        File contents as string (with trailing newline stripped)

    Raises:
        ValueError: If file doesn't exist, can't be read, or contains invalid UTF-8
    """
    # Check file exists
    if not resolved_path.exists():
        raise ValueError(
            f"Failed to read file for variable '{var_name}': {filepath}\n"
            f"File not found: {resolved_path}\n\n"
            f"Note: Relative paths are resolved from the recipe file location."
        )

    # Check it's a file (not directory)
    if not resolved_path.is_file():
        raise ValueError(
            f"Failed to read file for variable '{var_name}': {filepath}\n"
            f"Path is not a file: {resolved_path}"
        )

    # Read file with UTF-8 error handling
    try:
        content = resolved_path.read_text(encoding='utf-8')
    except PermissionError:
        raise ValueError(
            f"Failed to read file for variable '{var_name}': {filepath}\n"
            f"Permission denied: {resolved_path}\n\n"
            f"Ensure the file is readable by the current user."
        )
    except UnicodeDecodeError as e:
        raise ValueError(
            f"Failed to read file for variable '{var_name}': {filepath}\n"
            f"File contains invalid UTF-8 data: {resolved_path}\n\n"
            f"The {{ read: ... }} syntax only supports text files.\n"
            f"Error: {e}"
        )

    # Strip single trailing newline if present
    if content.endswith('\n'):
        content = content[:-1]

    return content


def _is_eval_reference(value: Any) -> bool:
    """Check if value is an eval command reference.

    Args:
        value: Raw value from YAML

    Returns:
        True if value is { eval: command } dict
    """
    return isinstance(value, dict) and "eval" in value


def _validate_eval_reference(var_name: str, value: dict) -> str:
    """Validate and extract command from eval reference.

    Args:
        var_name: Name of the variable being defined
        value: Dict that should be { eval: command }

    Returns:
        Command string

    Raises:
        ValueError: If reference is invalid
    """
    # Validate dict structure (only "eval" key allowed)
    if len(value) != 1:
        extra_keys = [k for k in value.keys() if k != "eval"]
        raise ValueError(
            f"Invalid eval reference in variable '{var_name}'.\n"
            f"Expected: {{ eval: command }}\n"
            f"Found extra keys: {', '.join(extra_keys)}"
        )

    command = value["eval"]

    # Validate command is provided and is a string
    if not command or not isinstance(command, str):
        raise ValueError(
            f"Invalid eval reference in variable '{var_name}'.\n"
            f"Expected: {{ eval: command }}\n"
            f"Found: {{ eval: {command!r} }}\n\n"
            f"Command must be a non-empty string."
        )

    return command


def _get_default_shell_and_args() -> tuple[str, list[str]]:
    """Get default shell and args for current platform.

    Returns:
        Tuple of (shell, args) for platform default
    """
    is_windows = platform.system() == "Windows"
    if is_windows:
        return ("cmd", ["/c"])
    else:
        return ("bash", ["-c"])


def _resolve_eval_variable(
    var_name: str,
    command: str,
    recipe_file_path: Path,
    recipe_data: dict
) -> str:
    """Execute command and capture output for variable value.

    Args:
        var_name: Name of the variable being defined
        command: Command to execute
        recipe_file_path: Path to recipe file (for working directory)
        recipe_data: Parsed YAML data (for accessing default_env)

    Returns:
        Command stdout as string (with trailing newline stripped)

    Raises:
        ValueError: If command fails or cannot be executed
    """
    # Determine shell to use
    shell = None
    shell_args = []

    # Check if recipe has default_env specified
    if recipe_data and "environments" in recipe_data:
        env_data = recipe_data["environments"]
        if isinstance(env_data, dict):
            default_env_name = env_data.get("default", "")
            if default_env_name and default_env_name in env_data:
                env_config = env_data[default_env_name]
                if isinstance(env_config, dict):
                    shell = env_config.get("shell", "")
                    shell_args = env_config.get("args", [])
                    if isinstance(shell_args, str):
                        shell_args = [shell_args]

    # Use platform default if no environment specified or not found
    if not shell:
        shell, shell_args = _get_default_shell_and_args()

    # Build command list
    cmd_list = [shell] + shell_args + [command]

    # Execute from recipe file directory
    working_dir = recipe_file_path.parent

    try:
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            cwd=working_dir,
            check=False,
        )
    except FileNotFoundError:
        raise ValueError(
            f"Failed to execute command for variable '{var_name}'.\n"
            f"Shell not found: {shell}\n\n"
            f"Command: {command}\n\n"
            f"Ensure the shell is installed and available in PATH."
        )
    except Exception as e:
        raise ValueError(
            f"Failed to execute command for variable '{var_name}'.\n"
            f"Command: {command}\n"
            f"Error: {e}"
        )

    # Check exit code
    if result.returncode != 0:
        stderr_output = result.stderr.strip() if result.stderr else "(no stderr output)"
        raise ValueError(
            f"Command failed for variable '{var_name}': {command}\n"
            f"Exit code: {result.returncode}\n"
            f"stderr: {stderr_output}\n\n"
            f"Ensure the command succeeds when run from the recipe file location."
        )

    # Get stdout and strip trailing newline
    output = result.stdout

    # Strip single trailing newline if present
    if output.endswith('\n'):
        output = output[:-1]

    return output


def _resolve_variable_value(
    name: str,
    raw_value: Any,
    resolved: dict[str, str],
    resolution_stack: list[str],
    file_path: Path,
    recipe_data: dict | None = None
) -> str:
    """Resolve a single variable value with circular reference detection.

    Args:
        name: Variable name being resolved
        raw_value: Raw value from YAML (int, str, bool, float, dict with env/read/eval)
        resolved: Dictionary of already-resolved variables
        resolution_stack: Stack of variables currently being resolved (for circular detection)
        file_path: Path to recipe file (for resolving relative file paths in { read: ... })
        recipe_data: Parsed YAML data (for accessing default_env in { eval: ... })

    Returns:
        Resolved string value

    Raises:
        ValueError: If circular reference detected or validation fails
    """
    # Check for circular reference
    if name in resolution_stack:
        cycle = " -> ".join(resolution_stack + [name])
        raise ValueError(f"Circular reference detected in variables: {cycle}")

    resolution_stack.append(name)

    try:
        # Check if this is an eval reference
        if _is_eval_reference(raw_value):
            # Validate and extract command
            command = _validate_eval_reference(name, raw_value)

            # Execute command and capture output
            string_value = _resolve_eval_variable(name, command, file_path, recipe_data)

            # Still perform variable-in-variable substitution
            from tasktree.substitution import substitute_variables
            try:
                resolved_value = substitute_variables(string_value, resolved)
            except ValueError as e:
                # Check if the undefined variable is in the resolution stack (circular reference)
                error_msg = str(e)
                if "not defined" in error_msg:
                    match = re.search(r"Variable '(\w+)' is not defined", error_msg)
                    if match:
                        undefined_var = match.group(1)
                        if undefined_var in resolution_stack:
                            cycle = " -> ".join(resolution_stack + [undefined_var])
                            raise ValueError(f"Circular reference detected in variables: {cycle}")
                # Re-raise the original error if not circular
                raise

            return resolved_value

        # Check if this is a file read reference
        if _is_file_read_reference(raw_value):
            # Validate and extract filepath
            filepath = _validate_file_read_reference(name, raw_value)

            # Resolve path (handles tilde, absolute, relative)
            resolved_path = _resolve_file_path(filepath, file_path)

            # Read file contents
            string_value = _resolve_file_variable(name, filepath, resolved_path)

            # Still perform variable-in-variable substitution
            from tasktree.substitution import substitute_variables
            try:
                resolved_value = substitute_variables(string_value, resolved)
            except ValueError as e:
                # Check if the undefined variable is in the resolution stack (circular reference)
                error_msg = str(e)
                if "not defined" in error_msg:
                    match = re.search(r"Variable '(\w+)' is not defined", error_msg)
                    if match:
                        undefined_var = match.group(1)
                        if undefined_var in resolution_stack:
                            cycle = " -> ".join(resolution_stack + [undefined_var])
                            raise ValueError(f"Circular reference detected in variables: {cycle}")
                # Re-raise the original error if not circular
                raise

            return resolved_value

        # Check if this is an environment variable reference
        if _is_env_variable_reference(raw_value):
            # Validate and extract env var name
            env_var_name = _validate_env_variable_reference(name, raw_value)

            # Resolve from os.environ
            string_value = _resolve_env_variable(name, env_var_name)

            # Still perform variable-in-variable substitution
            from tasktree.substitution import substitute_variables
            try:
                resolved_value = substitute_variables(string_value, resolved)
            except ValueError as e:
                # Check if the undefined variable is in the resolution stack (circular reference)
                error_msg = str(e)
                if "not defined" in error_msg:
                    match = re.search(r"Variable '(\w+)' is not defined", error_msg)
                    if match:
                        undefined_var = match.group(1)
                        if undefined_var in resolution_stack:
                            cycle = " -> ".join(resolution_stack + [undefined_var])
                            raise ValueError(f"Circular reference detected in variables: {cycle}")
                # Re-raise the original error if not circular
                raise

            return resolved_value

        # Validate and infer type
        type_name = _infer_variable_type(raw_value)
        from tasktree.types import get_click_type
        validator = get_click_type(type_name)

        # Validate and stringify the value
        string_value = validator.convert(raw_value, None, None)

        # Substitute any {{ var.name }} references in the string value
        from tasktree.substitution import substitute_variables
        try:
            resolved_value = substitute_variables(str(string_value), resolved)
        except ValueError as e:
            # Check if the undefined variable is in the resolution stack (circular reference)
            error_msg = str(e)
            if "not defined" in error_msg:
                # Extract the variable name from the error message
                import re
                match = re.search(r"Variable '(\w+)' is not defined", error_msg)
                if match:
                    undefined_var = match.group(1)
                    if undefined_var in resolution_stack:
                        cycle = " -> ".join(resolution_stack + [undefined_var])
                        raise ValueError(f"Circular reference detected in variables: {cycle}")
            # Re-raise the original error if not circular
            raise

        return resolved_value
    finally:
        resolution_stack.pop()


def _parse_variables_section(data: dict, file_path: Path) -> dict[str, str]:
    """Parse and resolve the variables section from YAML data.

    Variables are resolved in order, allowing variables to reference
    previously-defined variables using {{ var.name }} syntax.

    Args:
        data: Parsed YAML data (root level)
        file_path: Path to the recipe file (for resolving relative file paths)

    Returns:
        Dictionary mapping variable names to resolved string values

    Raises:
        ValueError: For validation errors, undefined refs, or circular refs
    """
    if "variables" not in data:
        return {}

    vars_data = data["variables"]
    if not isinstance(vars_data, dict):
        raise ValueError("'variables' must be a dictionary")

    resolved = {}  # name -> resolved string value
    resolution_stack = []  # For circular detection

    for var_name, raw_value in vars_data.items():
        _validate_variable_name(var_name)
        resolved[var_name] = _resolve_variable_value(
            var_name, raw_value, resolved, resolution_stack, file_path, data
        )

    return resolved


def _parse_file_with_env(
    file_path: Path,
    namespace: str | None,
    project_root: Path,
    import_stack: list[Path] | None = None,
) -> tuple[dict[str, Task], dict[str, Environment], str, dict[str, str]]:
    """Parse file and extract tasks, environments, and variables.

    Args:
        file_path: Path to YAML file
        namespace: Optional namespace prefix for tasks
        project_root: Root directory of the project
        import_stack: Stack of files being imported (for circular detection)

    Returns:
        Tuple of (tasks, environments, default_env_name, variables)
    """
    # Parse tasks normally
    tasks = _parse_file(file_path, namespace, project_root, import_stack)

    # Load YAML again to extract environments and variables (only from root file)
    environments: dict[str, Environment] = {}
    default_env = ""
    variables: dict[str, str] = {}

    # Only parse environments and variables from the root file (namespace is None)
    if namespace is None:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)

        # Parse variables first (so they can be used in environment preambles and tasks)
        if data:
            variables = _parse_variables_section(data, file_path)

        # Apply variable substitution to all tasks
        if variables:
            from tasktree.substitution import substitute_variables

            for task in tasks.values():
                task.cmd = substitute_variables(task.cmd, variables)
                task.desc = substitute_variables(task.desc, variables)
                task.working_dir = substitute_variables(task.working_dir, variables)
                task.inputs = [substitute_variables(inp, variables) for inp in task.inputs]
                task.outputs = [substitute_variables(out, variables) for out in task.outputs]
                # Substitute in argument default values (in arg spec strings)
                task.args = [substitute_variables(arg, variables) for arg in task.args]

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

                    # Parse common environment configuration
                    shell = env_config.get("shell", "")
                    args = env_config.get("args", [])
                    preamble = env_config.get("preamble", "")
                    working_dir = env_config.get("working_dir", "")

                    # Substitute variables in preamble
                    if preamble and variables:
                        from tasktree.substitution import substitute_variables
                        preamble = substitute_variables(preamble, variables)

                    # Parse Docker-specific fields
                    dockerfile = env_config.get("dockerfile", "")
                    context = env_config.get("context", "")
                    volumes = env_config.get("volumes", [])
                    ports = env_config.get("ports", [])
                    env_vars = env_config.get("env_vars", {})
                    extra_args = env_config.get("extra_args", [])
                    run_as_root = env_config.get("run_as_root", False)

                    # Validate environment type
                    if not shell and not dockerfile:
                        raise ValueError(
                            f"Environment '{env_name}' must specify either 'shell' "
                            f"(for shell environments) or 'dockerfile' (for Docker environments)"
                        )

                    # Validate Docker environment requirements
                    if dockerfile and not context:
                        raise ValueError(
                            f"Docker environment '{env_name}' must specify 'context' "
                            f"when 'dockerfile' is specified"
                        )

                    # Validate that Dockerfile exists if specified
                    if dockerfile:
                        dockerfile_path = project_root / dockerfile
                        if not dockerfile_path.exists():
                            raise ValueError(
                                f"Environment '{env_name}': Dockerfile not found at {dockerfile_path}"
                            )

                    # Validate that context directory exists if specified
                    if context:
                        context_path = project_root / context
                        if not context_path.exists():
                            raise ValueError(
                                f"Environment '{env_name}': context directory not found at {context_path}"
                            )
                        if not context_path.is_dir():
                            raise ValueError(
                                f"Environment '{env_name}': context must be a directory, got {context_path}"
                            )

                    # Validate environment name (must be valid Docker tag)
                    if not env_name.replace("-", "").replace("_", "").isalnum():
                        raise ValueError(
                            f"Environment name '{env_name}' must be alphanumeric "
                            f"(with optional hyphens and underscores)"
                        )

                    environments[env_name] = Environment(
                        name=env_name,
                        shell=shell,
                        args=args,
                        preamble=preamble,
                        dockerfile=dockerfile,
                        context=context,
                        volumes=volumes,
                        ports=ports,
                        env_vars=env_vars,
                        working_dir=working_dir,
                        extra_args=extra_args,
                        run_as_root=run_as_root
                    )

    return tasks, environments, default_env, variables


def parse_recipe(recipe_path: Path, project_root: Path | None = None) -> Recipe:
    """Parse a recipe file and handle imports recursively.

    Args:
        recipe_path: Path to the main recipe file
        project_root: Optional project root directory. If not provided, uses recipe file's parent directory.
                     When using --tasks option, this should be the current working directory.

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

    # Default project root to recipe file's parent if not specified
    if project_root is None:
        project_root = recipe_path.parent

    # Parse main file - it will recursively handle all imports
    tasks, environments, default_env, variables = _parse_file_with_env(
        recipe_path, namespace=None, project_root=project_root
    )

    return Recipe(
        tasks=tasks,
        project_root=project_root,
        environments=environments,
        default_env=default_env,
        variables=variables,
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

    # Default working directory is the project root (where tt is invoked)
    # NOT the directory where the tasks file is located
    default_working_dir = "."

    # Track local import namespaces for dependency rewriting
    local_import_namespaces: set[str] = set()

    # Process nested imports FIRST
    imports = data.get("imports", [])
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

    # Validate top-level keys (only imports, environments, tasks, and variables are allowed)
    VALID_TOP_LEVEL_KEYS = {"imports", "environments", "tasks", "variables"}

    # Check if tasks key is missing when there appear to be task definitions at root
    # Do this BEFORE checking for unknown keys, to provide better error message
    if "tasks" not in data and data:
        # Check if there are potential task definitions at root level
        potential_tasks = [
            k for k, v in data.items()
            if isinstance(v, dict) and k not in VALID_TOP_LEVEL_KEYS
        ]

        if potential_tasks:
            raise ValueError(
                f"Invalid recipe format in {file_path}\n\n"
                f"Task definitions must be under a top-level 'tasks:' key.\n\n"
                f"Found these keys at root level: {', '.join(potential_tasks)}\n\n"
                f"Did you mean:\n\n"
                f"tasks:\n"
                + '\n'.join(f"  {k}:" for k in potential_tasks) +
                "\n    cmd: ...\n\n"
                f"Valid top-level keys are: {', '.join(sorted(VALID_TOP_LEVEL_KEYS))}"
            )

    # Now check for other invalid top-level keys (non-dict values)
    invalid_keys = set(data.keys()) - VALID_TOP_LEVEL_KEYS
    if invalid_keys:
        raise ValueError(
            f"Invalid recipe format in {file_path}\n\n"
            f"Unknown top-level keys: {', '.join(sorted(invalid_keys))}\n\n"
            f"Valid top-level keys are:\n"
            f"  - imports      (for importing task files)\n"
            f"  - environments (for shell environment configuration)\n"
            f"  - tasks        (for task definitions)"
        )

    # Extract tasks from "tasks" key
    tasks_data = data.get("tasks", {})
    if tasks_data is None:
        tasks_data = {}

    # Process local tasks
    for task_name, task_data in tasks_data.items():

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
            env=task_data.get("env", ""),
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
