"""
Parse recipe YAML files and handle imports.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import KeysView
from typing import Any, List, Optional

import typer
import yaml

from tasktree.logging import Logger
from tasktree.types import get_click_type
from tasktree.process_runner import TaskOutputTypes


# Regex patterns for variable references
# Pattern for rewriting variable references (captures groups for substitution)
VAR_REFERENCE_REWRITE_PATTERN = re.compile(r"(\{\{\s*var\.)([^\s}]+)(\s*}})")

# Pattern for extracting variable names from references (single capture group)
VAR_REFERENCE_EXTRACT_PATTERN = re.compile(r"\{\{\s*var\s*\.\s*([^\s}]+)\s*}}")


class CircularImportError(Exception):
    """
    Raised when a circular import is detected.
    """

    pass


@dataclass
class ParsedFileResult:
    """
    Result of parsing a single YAML file, including tasks, runners, and raw variables.
    """

    tasks: dict[str, Any] = field(default_factory=dict)
    runners: dict[str, Any] = field(default_factory=dict)
    raw_variables: dict[str, Any] = field(default_factory=dict)
    name_errors: dict[str, str] = field(default_factory=dict)


@dataclass
class Runner:
    """
    Represents an execution runner configuration.

    Can be either a shell runner or a Docker runner:
    - Shell runner: has 'shell' field, executes directly on host
    - Docker runner: has 'dockerfile' field, executes in container
    """

    name: str
    shell: str = ""  # Path to shell (required for shell envs, optional for Docker)
    args: list[str] | dict[str, str] = field(
        default_factory=list
    )  # Shell args (list) or Docker build args (dict)
    preamble: str = ""
    # Docker-specific fields (presence of dockerfile indicates Docker environment)
    dockerfile: str = ""  # Path to Dockerfile
    context: str = ""  # Path to build context directory
    volumes: list[str] = field(default_factory=list)  # Volume mounts
    ports: list[str] = field(default_factory=list)  # Port mappings
    env_vars: dict[str, str] = field(default_factory=dict)  # Environment variables
    working_dir: str = ""  # Working directory (container or host)
    extra_args: List[str] = field(
        default_factory=list
    )  # Any extra arguments to pass to docker
    run_as_root: bool = False  # If True, skip user mapping (run as root in container)

    def __post_init__(self):
        """
        Ensure args is in the correct format.
        """
        if isinstance(self.args, str):
            self.args = [self.args]


@dataclass
class Task:
    """
    Represents a task definition.
    """

    name: str
    cmd: str
    desc: str = ""
    deps: list[str | dict[str, Any]] = field(
        default_factory=list
    )  # Can be strings or dicts with args
    inputs: list[str | dict[str, str]] = field(
        default_factory=list
    )  # Can be strings or dicts with named inputs
    outputs: list[str | dict[str, str]] = field(
        default_factory=list
    )  # Can be strings or dicts with named outputs
    working_dir: str = ""
    args: list[str | dict[str, Any]] = field(
        default_factory=list
    )  # Can be strings or dicts (each dict has single key: arg name)
    source_file: str = ""  # Track which file defined this task
    run_in: str = ""  # Runner name to use for execution
    private: bool = False  # If True, task is hidden from --list output
    pin_runner: bool = False  # If True, task's runner cannot be overridden
    task_output: TaskOutputTypes | None = None

    # Internal fields for efficient output lookup (built in __post_init__)
    _output_map: dict[str, str] = field(
        init=False, default_factory=dict, repr=False
    )  # name → path mapping
    _anonymous_outputs: list[str] = field(
        init=False, default_factory=list, repr=False
    )  # unnamed outputs

    # Internal fields for efficient input lookup (built in __post_init__)
    _input_map: dict[str, str] = field(
        init=False, default_factory=dict, repr=False
    )  # name → path mapping
    _anonymous_inputs: list[str] = field(
        init=False, default_factory=list, repr=False
    )  # unnamed inputs

    # Internal fields for positional input/output access (built in __post_init__)
    _indexed_inputs: list[str] = field(
        init=False, default_factory=list, repr=False
    )  # all inputs in YAML order
    _indexed_outputs: list[str] = field(
        init=False, default_factory=list, repr=False
    )  # all outputs in YAML order

    def __post_init__(self):
        """
        Ensure lists are always lists and build input/output maps and indexed lists.
        """
        if isinstance(self.deps, str):
            self.deps = [self.deps]
        if isinstance(self.inputs, str):
            self.inputs = [self.inputs]
        if isinstance(self.outputs, str):
            self.outputs = [self.outputs]
        if isinstance(self.args, str):
            self.args = [self.args]

        # Validate args is not a dict (common YAML mistake)
        if isinstance(self.args, dict):
            raise ValueError(
                f"Task '{self.name}' has invalid 'args' syntax.\n\n"
                f"Found dictionary syntax (without dashes):\n"
                f"  args:\n"
                f"    {list(self.args.keys())[0] if self.args else 'key'}: ...\n\n"
                f"Correct syntax uses list format (with dashes):\n"
                f"  args:\n"
                f"    - {list(self.args.keys())[0] if self.args else 'key'}: ...\n\n"
                f"Arguments must be defined as a list, not a dictionary."
            )

        # Build output maps for efficient lookup
        self._output_map = {}
        self._anonymous_outputs = []
        self._indexed_outputs = []

        for idx, output in enumerate(self.outputs):
            if isinstance(output, dict):
                # Named output: validate and store
                if len(output) != 1:
                    raise ValueError(
                        f"Task '{self.name}': Named output at index {idx} must have exactly one key-value pair, got {len(output)}: {output}"
                    )

                name, path = next(iter(output.items()))

                if not isinstance(path, str):
                    raise ValueError(
                        f"Task '{self.name}': Named output '{name}' must have a string path, got {type(path).__name__}: {path}"
                    )

                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
                    raise ValueError(
                        f"Task '{self.name}': Named output '{name}' must be a valid identifier "
                        f"(letters, numbers, underscores, cannot start with number)"
                    )

                if name in self._output_map:
                    raise ValueError(
                        f"Task '{self.name}': Duplicate output name '{name}' at index {idx}"
                    )

                self._output_map[name] = path
                self._indexed_outputs.append(path)
            elif isinstance(output, str):
                # Anonymous output: just store
                self._anonymous_outputs.append(output)
                self._indexed_outputs.append(output)
            else:
                raise ValueError(
                    f"Task '{self.name}': Output at index {idx} must be a string or dict, got {type(output).__name__}: {output}"
                )

        # Build input maps for efficient lookup
        self._input_map = {}
        self._anonymous_inputs = []
        self._indexed_inputs = []

        for idx, input_item in enumerate(self.inputs):
            if isinstance(input_item, dict):
                # Named input: validate and store
                if len(input_item) != 1:
                    raise ValueError(
                        f"Task '{self.name}': Named input at index {idx} must have exactly one key-value pair, got {len(input_item)}: {input_item}"
                    )

                name, path = next(iter(input_item.items()))

                if not isinstance(path, str):
                    raise ValueError(
                        f"Task '{self.name}': Named input '{name}' must have a string path, got {type(path).__name__}: {path}"
                    )

                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
                    raise ValueError(
                        f"Task '{self.name}': Named input '{name}' must be a valid identifier "
                        f"(letters, numbers, underscores, cannot start with number)"
                    )

                if name in self._input_map:
                    raise ValueError(
                        f"Task '{self.name}': Duplicate input name '{name}' at index {idx}"
                    )

                self._input_map[name] = path
                self._indexed_inputs.append(path)
            elif isinstance(input_item, str):
                # Anonymous input: just store
                self._anonymous_inputs.append(input_item)
                self._indexed_inputs.append(input_item)
            else:
                raise ValueError(
                    f"Task '{self.name}': Input at index {idx} must be a string or dict, got {type(input_item).__name__}: {input_item}"
                )


@dataclass
class DependencySpec:
    """
    Parsed dependency specification with potential template placeholders.

    This represents a dependency as defined in the recipe file, before template
    substitution. Argument values may contain {{ arg.* }} templates that will be
    substituted with parent task's argument values during graph construction.

    Attributes:
    task_name: Name of the dependency task
    arg_templates: Dictionary mapping argument names to string templates
    (None if no args specified). All values are strings, even
    for numeric types, to preserve template placeholders.
    """

    task_name: str
    arg_templates: dict[str, str] | None = None

    def __str__(self) -> str:
        """
        String representation for display.
        """
        if not self.arg_templates:
            return self.task_name
        args_str = ", ".join(f"{k}={v}" for k, v in self.arg_templates.items())
        return f"{self.task_name}({args_str})"


@dataclass
class DependencyInvocation:
    """
    Represents a task dependency invocation with optional arguments.

    Attributes:
    task_name: Name of the dependency task
    args: Dictionary of argument names to values (None if no args specified)
    """

    task_name: str
    args: dict[str, Any] | None = None

    def __str__(self) -> str:
        """
        String representation for display.
        """
        if not self.args:
            return self.task_name
        args_str = ", ".join(f"{k}={v}" for k, v in self.args.items())
        return f"{self.task_name}({args_str})"


@dataclass
class ArgSpec:
    """
    Represents a parsed argument specification.

    Attributes:
    name: Argument name
    arg_type: Type of the argument (str, int, float, bool, path)
    default: Default value as a string (None if no default)
    is_exported: Whether the argument is exported as an environment variable
    min_val: Minimum value for numeric arguments (None if not specified)
    max_val: Maximum value for numeric arguments (None if not specified)
    choices: List of valid choices for the argument (None if not specified)
    """

    name: str
    arg_type: str
    default: str | None = None
    is_exported: bool = False
    min_val: int | float | None = None
    max_val: int | float | None = None
    choices: list[Any] | None = None


@dataclass
class Recipe:
    """
    Represents a parsed recipe file with all tasks.
    """

    tasks: dict[str, Task]
    project_root: Path
    recipe_path: Path  # Path to the recipe file
    runners: dict[str, Runner] = field(default_factory=dict)
    default_runner: str = ""  # Name of default runner
    global_runner_override: str = ""  # Global runner override (set via CLI --run-in)
    variables: dict[str, str] = field(
        default_factory=dict
    )  # Global variables (resolved at parse time) - DEPRECATED, use evaluated_variables
    raw_variables: dict[str, Any] = field(
        default_factory=dict
    )  # Raw variable specs from YAML (not yet evaluated)
    evaluated_variables: dict[str, str] = field(
        default_factory=dict
    )  # Evaluated variable values (cached after evaluation)
    _variables_evaluated: bool = False  # Track if variables have been evaluated
    _original_yaml_data: dict[str, Any] = field(
        default_factory=dict
    )  # Store original YAML data for lazy evaluation context
    _name_errors: dict[str, str] = field(
        default_factory=dict
    )  # Deferred name validation errors (checked when items are reachable)

    def get_task(self, name: str) -> Task | None:
        """
        Get task by name.

        Args:
        name: Task name (may be namespaced like 'build.compile')

        Returns:
        Task if found, None otherwise
        """
        return self.tasks.get(name)

    def task_names(self) -> list[str]:
        """
        Get all task names.
        """
        return list(self.tasks.keys())

    def get_runner(self, name: str) -> Runner | None:
        """
        Get runner by name.

        Args:
        name: Runner name

        Returns:
        Runner if found, None otherwise
        """
        return self.runners.get(name)

    def evaluate_variables(self, root_task: str | None = None) -> None:
        """
        Evaluate variables lazily based on task reachability.

        This method implements lazy variable evaluation, which only evaluates
        variables that are actually reachable from the target task. This provides:
        - Performance improvement: expensive { eval: ... } commands only run when needed
        - Security improvement: sensitive { read: ... } files only accessed when needed
        - Side-effect control: commands with side effects only execute when necessary

        If root_task is provided, only variables used by reachable tasks are evaluated.
        If root_task is None, all variables are evaluated (for --list command compatibility).

        This method is idempotent - calling it multiple times is safe (uses caching).

        Args:
        root_task: Optional task name to determine reachability (None = evaluate all)

        Raises:
        ValueError: If variable evaluation or substitution fails

        Example:
        >>> recipe = parse_recipe(path)  # Variables not yet evaluated
        >>> recipe.evaluate_variables("build")  # Evaluate only reachable variables
        >>> # Now recipe.evaluated_variables contains only vars used by "build" task
        """
        if self._variables_evaluated:
            return  # Already evaluated, skip (idempotent)

        # Determine which variables to evaluate
        if root_task:
            # Lazy path: only evaluate reachable variables
            # If root_task doesn't exist, fall back to eager evaluation
            # (CLI will provide its own "Task not found" error)
            try:
                reachable_tasks = collect_reachable_tasks(self.tasks, root_task)
                variables_to_eval = collect_reachable_variables(
                    self.tasks, self.runners, reachable_tasks
                )
            except ValueError:
                # Root task not found - fall back to eager evaluation
                # This allows the recipe to be parsed even with invalid task names
                # so the CLI can provide its own error message
                reachable_tasks = self.tasks.keys()
                variables_to_eval = set(self.raw_variables.keys())
        else:
            # Eager path: evaluate all variables (for --list command)
            reachable_tasks = self.tasks.keys()
            variables_to_eval = set(self.raw_variables.keys())

        # Check for deferred name errors on reachable items
        self._check_reachable_name_errors(reachable_tasks, variables_to_eval)

        # Evaluate the selected variables using helper function
        self.evaluated_variables = _evaluate_variable_subset(
            self.raw_variables,
            variables_to_eval,
            self.recipe_path,
            self._original_yaml_data,
        )

        # Also update the deprecated 'variables' field for backward compatibility
        self.variables = self.evaluated_variables

        # Substitute evaluated variables into all tasks
        from tasktree.substitution import substitute_variables

        for task_name, task in self.tasks.items():
            if task_name not in reachable_tasks:
                continue

            task.cmd = substitute_variables(task.cmd, self.evaluated_variables)
            task.desc = substitute_variables(task.desc, self.evaluated_variables)
            task.working_dir = substitute_variables(
                task.working_dir, self.evaluated_variables
            )

            # Substitute variables in inputs (handle both string and dict inputs)
            resolved_inputs = []
            for inp in task.inputs:
                if isinstance(inp, str):
                    resolved_inputs.append(
                        substitute_variables(inp, self.evaluated_variables)
                    )
                elif isinstance(inp, dict):
                    # Named input: substitute the path value
                    resolved_dict = {}
                    for name, path in inp.items():
                        resolved_dict[name] = substitute_variables(
                            path, self.evaluated_variables
                        )
                    resolved_inputs.append(resolved_dict)
                else:
                    resolved_inputs.append(inp)
            task.inputs = resolved_inputs

            # Substitute variables in outputs (handle both string and dict outputs)
            resolved_outputs = []
            for out in task.outputs:
                if isinstance(out, str):
                    resolved_outputs.append(
                        substitute_variables(out, self.evaluated_variables)
                    )
                elif isinstance(out, dict):
                    # Named output: substitute the path value
                    resolved_dict = {}
                    for name, path in out.items():
                        resolved_dict[name] = substitute_variables(
                            path, self.evaluated_variables
                        )
                    resolved_outputs.append(resolved_dict)
                else:
                    resolved_outputs.append(out)
            task.outputs = resolved_outputs

            # Rebuild output maps after variable substitution
            task.__post_init__()

            # Substitute in argument default values (handle both string and dict args)
            resolved_args = []
            for arg in task.args:
                if isinstance(arg, str):
                    resolved_args.append(
                        substitute_variables(arg, self.evaluated_variables)
                    )
                elif isinstance(arg, dict):
                    # Dict arg: substitute in nested values (like default values)
                    resolved_dict = {}
                    for arg_name, arg_spec in arg.items():
                        if isinstance(arg_spec, dict):
                            # Substitute in the nested dict values (e.g., default, help, choices)
                            resolved_spec = {}
                            for key, value in arg_spec.items():
                                if isinstance(value, str):
                                    resolved_spec[key] = substitute_variables(
                                        value, self.evaluated_variables
                                    )
                                elif isinstance(value, list):
                                    # Handle lists like 'choices'
                                    resolved_spec[key] = [
                                        (
                                            substitute_variables(
                                                v, self.evaluated_variables
                                            )
                                            if isinstance(v, str)
                                            else v
                                        )
                                        for v in value
                                    ]
                                else:
                                    resolved_spec[key] = value
                            resolved_dict[arg_name] = resolved_spec
                        else:
                            # Simple value
                            resolved_dict[arg_name] = (
                                substitute_variables(arg_spec, self.evaluated_variables)
                                if isinstance(arg_spec, str)
                                else arg_spec
                            )
                    resolved_args.append(resolved_dict)
                else:
                    resolved_args.append(arg)
            task.args = resolved_args

        # Substitute evaluated variables into all runners
        for env in self.runners.values():
            if env.preamble:
                env.preamble = substitute_variables(
                    env.preamble, self.evaluated_variables
                )

            # Substitute in volumes
            if env.volumes:
                env.volumes = [
                    substitute_variables(vol, self.evaluated_variables)
                    for vol in env.volumes
                ]

            # Substitute in ports
            if env.ports:
                env.ports = [
                    substitute_variables(port, self.evaluated_variables)
                    for port in env.ports
                ]

            # Substitute in env_vars values
            if env.env_vars:
                env.env_vars = {
                    key: substitute_variables(value, self.evaluated_variables)
                    for key, value in env.env_vars.items()
                }

            # Substitute in working_dir
            if env.working_dir:
                env.working_dir = substitute_variables(
                    env.working_dir, self.evaluated_variables
                )

            # Substitute in build args (dict for Docker environments)
            if env.args and isinstance(env.args, dict):
                env.args = {
                    key: substitute_variables(str(value), self.evaluated_variables)
                    for key, value in env.args.items()
                }

        # Mark as evaluated
        self._variables_evaluated = True

    def _collect_variable_name_errors(
        self, reachable_variables: set[str]
    ) -> list[str]:
        """
        Collect name errors for reachable variables.

        Args:
            reachable_variables: Set of variable names that are reachable from target tasks

        Returns:
            List of error messages for variables with invalid names
        """
        errors = []
        if self._name_errors:
            for var_name in reachable_variables:
                if var_name in self._name_errors:
                    errors.append(self._name_errors[var_name])
        return errors

    def _collect_reachable_runners(
        self, reachable_tasks: set[str] | KeysView
    ) -> set[str]:
        """
        Collect all runner names referenced by reachable tasks.

        Args:
            reachable_tasks: Set or KeysView of task names that are reachable from target tasks

        Returns:
            Set of runner names that are referenced by the reachable tasks
        """
        return {
            self.tasks[t].run_in
            for t in reachable_tasks
            if t in self.tasks and self.tasks[t].run_in
        }

    def _collect_runner_errors(
        self, reachable_runners: set[str], reachable_tasks: set[str] | KeysView
    ) -> list[str]:
        """
        Collect name errors and non-existent runner errors for reachable runners.

        Args:
            reachable_runners: Set of runner names referenced by reachable tasks
            reachable_tasks: Set or KeysView of task names that are reachable from target tasks

        Returns:
            List of error messages for runners with invalid names or that don't exist
        """
        errors = []
        for runner_name in reachable_runners:
            # Check for name errors (dots, empty names)
            if self._name_errors and runner_name in self._name_errors:
                errors.append(self._name_errors[runner_name])
            # Check for non-existent runners
            elif runner_name not in self.runners:
                # Find which task(s) reference this non-existent runner
                referencing_tasks = [
                    t
                    for t in reachable_tasks
                    if t in self.tasks and self.tasks[t].run_in == runner_name
                ]
                for task_name in referencing_tasks:
                    errors.append(
                        f"Task '{task_name}' specifies run_in with invalid runner: '{runner_name}'"
                    )
        return errors

    def _check_reachable_name_errors(
        self,
        reachable_tasks: set[str] | KeysView,
        reachable_variables: set[str],
    ) -> None:
        """Raise ValueError if any reachable variable or runner has a name error, or if any reachable task references a non-existent runner."""
        errors = []

        # Check for name errors on reachable variables
        errors.extend(self._collect_variable_name_errors(reachable_variables))

        # Check for name errors on reachable runners AND non-existent runners
        reachable_runners = self._collect_reachable_runners(reachable_tasks)
        errors.extend(self._collect_runner_errors(reachable_runners, reachable_tasks))

        if errors:
            raise ValueError("; ".join(errors))


def find_recipe_file(start_dir: Path | None = None) -> Path | None:
    """
    Find recipe file in current or parent directories.

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

        # Check for exact filenames first (these are preferred)
        for filename in ["tasktree.yaml", "tasktree.yml", "tt.yaml", "tt.yml"]:
            recipe_path = current / filename
            if recipe_path.exists():
                candidates.append(recipe_path)

        # If we found standard recipe files, use the first one
        if len(candidates) > 1:
            # Multiple standard recipe files found - ambiguous
            filenames = [c.name for c in candidates]
            raise ValueError(
                f"Multiple recipe files found in {current}:\n"
                f"  {', '.join(filenames)}\n\n"
                f"Please specify which file to use with --tasks (-T):\n"
                f"  tt --tasks {filenames[0]} <task-name>"
            )
        elif len(candidates) == 1:
            return candidates[0]

        # Only check for *.tasks files if no standard recipe files found
        # (*.tasks files are typically imports, not main recipes)
        tasks_files = []
        globs = ["*.tasks", "*.tt"]
        for g in globs:
            for tasks_file in current.glob(g):
                if tasks_file.is_file():
                    tasks_files.append(tasks_file)

        if len(tasks_files) > 1:
            # Multiple *.tasks files found - ambiguous
            filenames = [t.name for t in tasks_files]
            raise ValueError(
                f"Multiple recipe files found in {current}:\n"
                f"  {', '.join(filenames)}\n\n"
                f"Please specify which file to use with --tasks (-T):\n"
                f"  tt --tasks {filenames[0]} <task-name>"
            )
        elif len(tasks_files) == 1:
            return tasks_files[0]

        # Move to parent directory
        parent = current.parent
        if parent == current:
            # Reached root
            break
        current = parent

    return None





def _validate_local_item_name(name: str, kind: str) -> str | None:
    """Return an error message if the local name is invalid, None otherwise."""
    if not name:
        return f"{kind} name must not be empty"
    if "." in name:
        return f"{kind} name '{name}' must not contain dots (reserved for import namespacing)"
    return None


def _rewrite_variable_references(text: str, namespace: str) -> str:
    """
    Rewrite {{ var.X }} references in text to {{ var.namespace.X }}.

    Args:
    text: Text containing {{ var.* }} placeholders
    namespace: Namespace prefix to prepend to variable names

    Returns:
    Text with variable references rewritten
    """
    assert namespace, "namespace must not be empty"
    return VAR_REFERENCE_REWRITE_PATTERN.sub(
        rf"\g<1>{namespace}.\2\3",
        text,
    )


def _rewrite_variable_references_in_raw_value(
    raw_value: Any, namespace: str
) -> Any:
    """
    Rewrite {{ var.X }} references within a raw variable value.

    Handles string values, and dict values (env with default, read, eval).

    Args:
    raw_value: Raw variable value from YAML
    namespace: Namespace prefix to prepend to variable names

    Returns:
    Raw value with variable references rewritten
    """
    assert namespace, "namespace must not be empty"
    if isinstance(raw_value, str):
        return _rewrite_variable_references(raw_value, namespace)
    elif isinstance(raw_value, dict):
        rewritten = {}
        for key, val in raw_value.items():
            if isinstance(val, str):
                rewritten[key] = _rewrite_variable_references(val, namespace)
            else:
                rewritten[key] = val
        return rewritten
    return raw_value


def _rewrite_io_variable_references(
    items: list[str | dict[str, str]], namespace: str
) -> list[str | dict[str, str]]:
    """
    Rewrite {{ var.X }} references in a list of inputs or outputs.

    Items can be strings (anonymous) or single-key dicts (named).
    """
    assert namespace, "namespace must not be empty"
    rewritten = []
    for item in items:
        if isinstance(item, str):
            rewritten.append(_rewrite_variable_references(item, namespace))
        elif isinstance(item, dict):
            rewritten.append(
                {k: _rewrite_variable_references(v, namespace) if isinstance(v, str) else v
                 for k, v in item.items()}
            )
        else:
            rewritten.append(item)
    return rewritten


def _rewrite_args_variable_references(
    args: list[str | dict[str, Any]], namespace: str
) -> list[str | dict[str, Any]]:
    """
    Rewrite {{ var.X }} references in a list of argument specs.

    Args can be strings or single-key dicts with nested config dicts.
    """
    assert namespace, "namespace must not be empty"
    rewritten = []
    for arg in args:
        if isinstance(arg, str):
            rewritten.append(_rewrite_variable_references(arg, namespace))
        elif isinstance(arg, dict):
            rewritten_arg = {}
            for arg_name, config in arg.items():
                if isinstance(config, dict):
                    rewritten_config = {}
                    for key, val in config.items():
                        if isinstance(val, str):
                            rewritten_config[key] = _rewrite_variable_references(val, namespace)
                        elif isinstance(val, list) and key == "choices":
                            rewritten_config[key] = [
                                _rewrite_variable_references(c, namespace) if isinstance(c, str) else c
                                for c in val
                            ]
                        else:
                            rewritten_config[key] = val
                    rewritten_arg[arg_name] = rewritten_config
                else:
                    rewritten_arg[arg_name] = config
            rewritten.append(rewritten_arg)
        else:
            rewritten.append(arg)
    return rewritten


def _rewrite_task_variable_references(task: "Task", namespace: str) -> None:
    """
    Rewrite {{ var.X }} references in all fields of a task to {{ var.namespace.X }}.
    Modifies the task in place.
    """
    assert namespace, "namespace must not be empty"
    task.cmd = _rewrite_variable_references(task.cmd, namespace)
    task.desc = _rewrite_variable_references(task.desc, namespace)
    task.working_dir = _rewrite_variable_references(task.working_dir, namespace)
    task.inputs = _rewrite_io_variable_references(task.inputs, namespace)
    task.outputs = _rewrite_io_variable_references(task.outputs, namespace)
    task.args = _rewrite_args_variable_references(task.args, namespace)
    # Rebuild internal maps after modifying inputs/outputs
    task.__post_init__()


def _rewrite_runner_variable_references(runner: "Runner", namespace: str) -> None:
    """
    Rewrite {{ var.X }} references in all fields of a runner to {{ var.namespace.X }}.
    Modifies the runner in place.
    """
    assert namespace, "namespace must not be empty"
    runner.preamble = _rewrite_variable_references(runner.preamble, namespace)
    runner.dockerfile = _rewrite_variable_references(runner.dockerfile, namespace)
    runner.context = _rewrite_variable_references(runner.context, namespace)
    runner.working_dir = _rewrite_variable_references(runner.working_dir, namespace)
    runner.volumes = [_rewrite_variable_references(v, namespace) for v in runner.volumes]
    runner.ports = [_rewrite_variable_references(p, namespace) for p in runner.ports]
    runner.env_vars = {
        k: _rewrite_variable_references(v, namespace) for k, v in runner.env_vars.items()
    }
    runner.extra_args = [_rewrite_variable_references(a, namespace) for a in runner.extra_args]


def _infer_variable_type(value: Any) -> str:
    """
    Infer type name from Python value.

    Args:
    value: Python value from YAML

    Returns:
    Type name string (str, int, float, bool)

    Raises:
    ValueError: If value type is not supported
    """
    type_map = {str: "str", int: "int", float: "float", bool: "bool"}
    python_type = type(value)
    if python_type not in type_map:
        raise ValueError(
            f"Variable has unsupported type '{python_type.__name__}'. "
            f"Supported types: str, int, float, bool, path, datetime, ip, ipv4, ipv6, email, hostname"
        )
    return type_map[python_type]


def _is_env_variable_reference(value: Any) -> bool:
    """
    Check if value is an environment variable reference.

    Args:
    value: Raw value from YAML

    Returns:
    True if value is { env: VAR_NAME } dict
    """
    return isinstance(value, dict) and "env" in value


def _validate_env_variable_reference(
    var_name: str, value: dict
) -> tuple[str, str | None]:
    """
    Validate and extract environment variable name and optional default from reference.

    Args:
    var_name: Name of the variable being defined
    value: Dict that should be { env: ENV_VAR_NAME } or { env: ENV_VAR_NAME, default: "value" }

    Returns:
    Tuple of (environment variable name, default value or None)

    Raises:
    ValueError: If reference is invalid
    """
    # Validate dict structure - allow 'env' and optionally 'default'
    valid_keys = {"env", "default"}
    invalid_keys = set(value.keys()) - valid_keys
    if invalid_keys:
        raise ValueError(
            f"Invalid environment variable reference in variable '{var_name}'.\n"
            f'Expected: {{ env: VARIABLE_NAME }} or {{ env: VARIABLE_NAME, default: "value" }}\n'
            f"Found invalid keys: {', '.join(invalid_keys)}"
        )

    # Validate 'env' key is present
    if "env" not in value:
        raise ValueError(
            f"Invalid environment variable reference in variable '{var_name}'.\n"
            f"Missing required 'env' key.\n"
            f'Expected: {{ env: VARIABLE_NAME }} or {{ env: VARIABLE_NAME, default: "value" }}'
        )

    env_var_name = value["env"]

    # Validate env var name is provided
    if not env_var_name or not isinstance(env_var_name, str):
        raise ValueError(
            f"Invalid environment variable reference in variable '{var_name}'.\n"
            f'Expected: {{ env: VARIABLE_NAME }} or {{ env: VARIABLE_NAME, default: "value" }}'
            f"Found: {{ env: {env_var_name!r} }}"
        )

    # Validate env var name format (allow both uppercase and mixed case for flexibility)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", env_var_name):
        raise ValueError(
            f"Invalid environment variable name '{env_var_name}' in variable '{var_name}'.\n"
            f"Environment variable names must start with a letter or underscore,\n"
            f"and contain only alphanumerics and underscores."
        )

    # Extract and validate default if present
    default = value.get("default")
    if default is not None:
        # Default must be a string (env vars are always strings)
        if not isinstance(default, str):
            raise ValueError(
                f"Invalid default value in variable '{var_name}'.\n"
                f"Environment variable defaults must be strings.\n"
                f"Got: {default!r} (type: {type(default).__name__})\n"
                f'Use a quoted string: {{ env: {env_var_name}, default: "{default}" }}'
            )

    return env_var_name, default


def _resolve_env_variable(
    var_name: str, env_var_name: str, default: str | None = None
) -> str:
    """
    Resolve environment variable value.

    Args:
    var_name: Name of the variable being defined
    env_var_name: Name of environment variable to read
    default: Optional default value to use if environment variable is not set

    Returns:
    Environment variable value as string, or default if not set and default provided

    Raises:
    ValueError: If environment variable is not set and no default provided
    """
    value = os.environ.get(env_var_name, default)

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
    """
    Check if value is a file read reference.

    Args:
    value: Raw value from YAML

    Returns:
    True if value is { read: filepath } dict
    """
    return isinstance(value, dict) and "read" in value


def _validate_file_read_reference(var_name: str, value: dict) -> str:
    """
    Validate and extract filepath from file read reference.

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
    """
    Resolve file path relative to recipe file location.

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
    """
    Read file contents for variable value.

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
        content = resolved_path.read_text(encoding="utf-8")
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
    if content.endswith("\n"):
        content = content[:-1]

    return content


def _is_eval_reference(value: Any) -> bool:
    """
    Check if value is an eval command reference.

    Args:
    value: Raw value from YAML

    Returns:
    True if value is { eval: command } dict
    """
    return isinstance(value, dict) and "eval" in value


def _validate_eval_reference(var_name: str, value: dict) -> str:
    """
    Validate and extract command from eval reference.

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
    """
    Get default shell and args for current platform.

    Returns:
    Tuple of (shell, args) for platform default
    """
    is_windows = platform.system() == "Windows"
    if is_windows:
        return "cmd", ["/c"]
    else:
        return "bash", ["-c"]


def _resolve_eval_variable(
    var_name: str, command: str, recipe_file_path: Path, recipe_data: dict
) -> str:
    """
    Execute command and capture output for variable value.

    Args:
    var_name: Name of the variable being defined
    command: Command to execute
    recipe_file_path: Path to recipe file (for working directory)
    recipe_data: Parsed YAML data (for accessing default_runner)

    Returns:
    Command stdout as string (with trailing newline stripped)

    Raises:
    ValueError: If command fails or cannot be executed
    """
    # Determine shell to use
    shell = None
    shell_args = []

    # Check if recipe has default_runner specified
    if recipe_data and "runners" in recipe_data:
        env_data = recipe_data["runners"]
        if isinstance(env_data, dict):
            default_runner_name = env_data.get("default", "")
            if default_runner_name and default_runner_name in env_data:
                env_config = env_data[default_runner_name]
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
    if output.endswith("\n"):
        output = output[:-1]

    return output


def _resolve_variable_value(
    name: str,
    raw_value: Any,
    resolved: dict[str, str],
    resolution_stack: list[str],
    file_path: Path,
    recipe_data: dict | None = None,
) -> str:
    """
    Resolve a single variable value with circular reference detection.

    Args:
    name: Variable name being resolved
    raw_value: Raw value from YAML (int, str, bool, float, dict with env/read/eval)
    resolved: Dictionary of already-resolved variables
    resolution_stack: Stack of variables currently being resolved (for circular detection)
    file_path: Path to recipe file (for resolving relative file paths in { read: ... })
    recipe_data: Parsed YAML data (for accessing default_runner in { eval: ... })

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
                    match = re.search(r"Variable '([\w.]+)' is not defined", error_msg)
                    if match:
                        undefined_var = match.group(1)
                        if undefined_var in resolution_stack:
                            cycle = " -> ".join(resolution_stack + [undefined_var])
                            raise ValueError(
                                f"Circular reference detected in variables: {cycle}"
                            )
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
                    match = re.search(r"Variable '([\w.]+)' is not defined", error_msg)
                    if match:
                        undefined_var = match.group(1)
                        if undefined_var in resolution_stack:
                            cycle = " -> ".join(resolution_stack + [undefined_var])
                            raise ValueError(
                                f"Circular reference detected in variables: {cycle}"
                            )
                # Re-raise the original error if not circular
                raise

            return resolved_value

        # Check if this is an environment variable reference
        if _is_env_variable_reference(raw_value):
            # Validate and extract env var name and optional default
            env_var_name, default = _validate_env_variable_reference(name, raw_value)

            # Resolve from os.environ (with optional default)
            string_value = _resolve_env_variable(name, env_var_name, default)

            # Still perform variable-in-variable substitution
            from tasktree.substitution import substitute_variables

            try:
                resolved_value = substitute_variables(string_value, resolved)
            except ValueError as e:
                # Check if the undefined variable is in the resolution stack (circular reference)
                error_msg = str(e)
                if "not defined" in error_msg:
                    match = re.search(r"Variable '([\w.]+)' is not defined", error_msg)
                    if match:
                        undefined_var = match.group(1)
                        if undefined_var in resolution_stack:
                            cycle = " -> ".join(resolution_stack + [undefined_var])
                            raise ValueError(
                                f"Circular reference detected in variables: {cycle}"
                            )
                # Re-raise the original error if not circular
                raise

            return resolved_value

        # Validate and infer type
        type_name = _infer_variable_type(raw_value)
        from tasktree.types import get_click_type

        validator = get_click_type(type_name)

        # Validate and stringify the value
        string_value = validator.convert(raw_value, None, None)

        # Convert to string (lowercase for booleans to match YAML/shell conventions)
        if isinstance(string_value, bool):
            string_value_str = str(string_value).lower()
        else:
            string_value_str = str(string_value)

        # Substitute any {{ var.name }} references in the string value
        from tasktree.substitution import substitute_variables

        try:
            resolved_value = substitute_variables(string_value_str, resolved)
        except ValueError as e:
            # Check if the undefined variable is in the resolution stack (circular reference)
            error_msg = str(e)
            if "not defined" in error_msg:
                # Extract the variable name from the error message
                match = re.search(r"Variable '([\w.]+)' is not defined", error_msg)
                if match:
                    undefined_var = match.group(1)
                    if undefined_var in resolution_stack:
                        cycle = " -> ".join(resolution_stack + [undefined_var])
                        raise ValueError(
                            f"Circular reference detected in variables: {cycle}"
                        )
            # Re-raise the original error if not circular
            raise

        return resolved_value
    finally:
        resolution_stack.pop()


def _parse_variables_section(data: dict, file_path: Path) -> dict[str, str]:
    """
    Parse and resolve the variables section from YAML data.

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
        resolved[var_name] = _resolve_variable_value(
            var_name, raw_value, resolved, resolution_stack, file_path, data
        )

    return resolved


def _expand_variable_dependencies(
    variable_names: set[str], raw_variables: dict[str, Any]
) -> set[str]:
    """
    Expand variable set to include all transitively referenced variables.

    If variable A references variable B, and B references C, then requesting A
    should also evaluate B and C.

    Args:
    variable_names: Initial set of variable names
    raw_variables: Raw variable definitions from YAML

    Returns:
    Expanded set including all transitively referenced variables

    Example:
    >>> raw_vars = {
    ...     "a": "{{ var.b }}",
    ...     "b": "{{ var.c }}",
    ...     "c": "value"
    ... }
    >>> _expand_variable_dependencies({"a"}, raw_vars)
    {"a", "b", "c"}
    """
    expanded = set(variable_names)
    to_process = list(variable_names)

    while to_process:
        var_name = to_process.pop(0)

        if var_name not in raw_variables:
            continue

        raw_value = raw_variables[var_name]

        # Extract referenced variables from the raw value
        # Handle string values with {{ var.* }} patterns
        if isinstance(raw_value, str):
            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(raw_value):
                referenced_var = match.group(1)
                if referenced_var not in expanded:
                    expanded.add(referenced_var)
                    to_process.append(referenced_var)
        # Handle { read: filepath } variables - check file contents for variable references
        elif isinstance(raw_value, dict) and "read" in raw_value:
            filepath = raw_value["read"]
            # For dependency expansion, we speculatively read files to find variable references
            # This is acceptable because file reads are relatively cheap compared to eval commands
            try:
                # Try to read the file (may not exist yet, which is fine for dependency tracking)
                # Skip if filepath is None or empty (validation error will be caught during evaluation)
                if filepath and isinstance(filepath, str):
                    from pathlib import Path

                    if Path(filepath).exists():
                        file_content = Path(filepath).read_text()
                        # Extract variable references from file content
                        for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(file_content):
                            referenced_var = match.group(1)
                            if referenced_var not in expanded:
                                expanded.add(referenced_var)
                                to_process.append(referenced_var)
            except (IOError, OSError, TypeError):
                # If file can't be read during expansion, that's okay
                # The error will be caught during actual evaluation
                pass
        # Handle { env: VAR, default: ... } variables - check default value for variable references
        elif (
            isinstance(raw_value, dict)
            and "env" in raw_value
            and "default" in raw_value
        ):
            default_value = raw_value["default"]
            # Check if default value contains variable references
            if isinstance(default_value, str):
                for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(default_value):
                    referenced_var = match.group(1)
                    if referenced_var not in expanded:
                        expanded.add(referenced_var)
                        to_process.append(referenced_var)

    return expanded


def _evaluate_variable_subset(
    raw_variables: dict[str, Any], variable_names: set[str], file_path: Path, data: dict
) -> dict[str, str]:
    """
    Evaluate only specified variables from raw specs (for lazy evaluation).

    This function is similar to _parse_variables_section but only evaluates
    a subset of variables. This enables lazy evaluation where only reachable
    variables are evaluated, improving performance and security.

    Transitive dependencies are automatically included: if variable A references
    variable B, both will be evaluated even if only A was explicitly requested.

    Args:
    raw_variables: Raw variable definitions from YAML (not yet evaluated)
    variable_names: Set of variable names to evaluate
    file_path: Recipe file path (for relative file resolution)
    data: Full YAML data (for context in _resolve_variable_value)

    Returns:
    Dictionary of evaluated variable values (for specified variables and their dependencies)

    Raises:
    ValueError: For validation errors, undefined refs, or circular refs

    Example:
    >>> raw_vars = {"a": "{{ var.b }}", "b": "value", "c": "unused"}
    >>> _evaluate_variable_subset(raw_vars, {"a"}, path, data)
    {"a": "value", "b": "value"}  # "a" and its dependency "b", but not "c"
    """
    if not isinstance(raw_variables, dict):
        raise ValueError("'variables' must be a dictionary")

    # Expand variable set to include transitive dependencies
    variables_to_eval = _expand_variable_dependencies(variable_names, raw_variables)

    resolved = {}  # name -> resolved string value
    resolution_stack = []  # For circular detection

    # Evaluate variables in order (to handle references between variables)
    for var_name, raw_value in raw_variables.items():
        if var_name in variables_to_eval:
            resolved[var_name] = _resolve_variable_value(
                var_name, raw_value, resolved, resolution_stack, file_path, data
            )

    return resolved


def _parse_runners_from_data(
    data: dict[str, Any], project_root: Path
) -> tuple[dict[str, Runner], str]:
    """
    Parse runner definitions from YAML data.

    Args:
    data: Parsed YAML data containing a 'runners' section
    project_root: Root directory of the project (for validating Dockerfile/context paths)

    Returns:
    Tuple of (runners dict, default_runner_name)
    """
    runners: dict[str, Runner] = {}
    default_runner = ""

    if not data or "runners" not in data:
        return runners, default_runner

    env_data = data["runners"]
    if not isinstance(env_data, dict):
        return runners, default_runner

    # Extract default environment name
    default_runner = env_data.get("default", "")

    # Parse each runner definition
    for env_name, env_config in env_data.items():
        if env_name == "default":
            continue  # Skip the default key itself

        if not isinstance(env_config, dict):
            raise ValueError(f"Runner '{env_name}' must be a dictionary")

        # Parse common runner configuration
        shell = env_config.get("shell", "")
        args = env_config.get("args", [])
        preamble = env_config.get("preamble", "")
        working_dir = env_config.get("working_dir", "")

        # SKIP variable substitution in preamble - defer to lazy evaluation
        # preamble may contain {{ var.* }} placeholders

        # Parse Docker-specific fields
        dockerfile = env_config.get("dockerfile", "")
        context = env_config.get("context", "")
        volumes = env_config.get("volumes", [])
        ports = env_config.get("ports", [])
        env_vars = env_config.get("env_vars", {})
        extra_args = env_config.get("extra_args", [])
        run_as_root = env_config.get("run_as_root", False)

        # SKIP variable substitution in runner fields - defer to lazy evaluation
        # Runner fields may contain {{ var.* }} placeholders

        # Validate runner type
        if not shell and not dockerfile:
            raise ValueError(
                f"Runner '{env_name}' must specify either 'shell' "
                f"(for shell runners) or 'dockerfile' (for Docker runners)"
            )

        # Validate Docker runner requirements
        if dockerfile and not context:
            raise ValueError(
                f"Docker runner '{env_name}' must specify 'context' "
                f"when 'dockerfile' is specified"
            )

        # Validate that Dockerfile exists if specified
        if dockerfile:
            dockerfile_path = project_root / dockerfile
            if not dockerfile_path.exists():
                raise ValueError(
                    f"Runner '{env_name}': Dockerfile not found at {dockerfile_path}"
                )

        # Validate that context directory exists if specified
        if context:
            context_path = project_root / context
            if not context_path.exists():
                raise ValueError(
                    f"Runner '{env_name}': context directory not found at {context_path}"
                )
            if not context_path.is_dir():
                raise ValueError(
                    f"Runner '{env_name}': context must be a directory, got {context_path}"
                )

        runners[env_name] = Runner(
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
            run_as_root=run_as_root,
        )

    return runners, default_runner


def _extract_and_validate_variables(
    data: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Extract raw variables from YAML data and validate their names.

    Args:
        data: Parsed YAML data

    Returns:
        Tuple of (raw_variables, name_errors)
    """
    raw_variables: dict[str, Any] = {}
    name_errors: dict[str, str] = {}

    if data and "variables" in data:
        raw_variables = data["variables"]
        for var_name in raw_variables:
            error = _validate_local_item_name(var_name, "Variable")
            if error:
                name_errors[var_name] = error

    return raw_variables, name_errors


def _extract_and_validate_runners(
    data: dict[str, Any] | None, project_root: Path
) -> tuple[dict[str, Runner], str, dict[str, str]]:
    """
    Extract runners from YAML data and validate their names.

    Args:
        data: Parsed YAML data
        project_root: Root directory of the project

    Returns:
        Tuple of (runners, default_runner_name, name_errors)
    """
    name_errors: dict[str, str] = {}
    runners, default_runner = _parse_runners_from_data(data, project_root)

    for runner_name in runners:
        error = _validate_local_item_name(runner_name, "Runner")
        if error:
            name_errors[runner_name] = error

    return runners, default_runner, name_errors


def _parse_file_with_env(
    file_path: Path,
    namespace: str | None,
    project_root: Path,
    import_stack: list[Path] | None = None,
) -> tuple[dict[str, Task], dict[str, Runner], str, dict[str, Any], dict[str, Any], dict[str, str]]:
    """
    Parse file and extract tasks, runners, and variables.

    Args:
    file_path: Path to YAML file
    namespace: Optional namespace prefix for tasks
    project_root: Root directory of the project
    import_stack: Stack of files being imported (for circular detection)

    Returns:
    Tuple of (tasks, runners, default_runner_name, raw_variables, YAML_data, name_errors)
    Note: Variables are NOT evaluated here - they're stored as raw specs for lazy evaluation
    """
    # Parse tasks normally
    parsed = _parse_file(file_path, namespace, project_root, import_stack)
    tasks = parsed.tasks
    name_errors: dict[str, str] = dict(parsed.name_errors)

    # Load YAML again to extract runners and variables (only from root file)
    runners: dict[str, Runner] = {}
    default_runner = ""
    raw_variables: dict[str, Any] = {}
    yaml_data: dict[str, Any] = {}

    # Only parse runners and variables from the root file (namespace is None)
    if namespace is None:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
            yaml_data = data or {}

        # Extract and validate variables
        raw_variables, var_errors = _extract_and_validate_variables(data)
        name_errors.update(var_errors)

        # Extract and validate runners
        runners, default_runner, runner_errors = _extract_and_validate_runners(
            data, project_root
        )
        name_errors.update(runner_errors)

    # Merge runners and variables from imported files
    runners.update(parsed.runners)
    raw_variables.update(parsed.raw_variables)

    return tasks, runners, default_runner, raw_variables, yaml_data, name_errors


def collect_reachable_tasks(tasks: dict[str, Task], root_task: str) -> set[str]:
    """
    Collect all tasks reachable from the root task via dependencies.

    Uses BFS to traverse the dependency graph and collect all task names
    that could potentially be executed when running the root task.

    Args:
    tasks: Dictionary mapping task names to Task objects
    root_task: Name of the root task to start traversal from

    Returns:
    Set of task names reachable from root_task (includes root_task itself)

    Raises:
    ValueError: If root_task doesn't exist

    Example:
    >>> tasks = {"a": Task("a", deps=["b"]), "b": Task("b", deps=[]), "c": Task("c", deps=[])}
    >>> collect_reachable_tasks(tasks, "a")
    {"a", "b"}
    """
    if root_task not in tasks:
        raise ValueError(f"Root task '{root_task}' not found in recipe")

    reachable = set()
    queue = [root_task]

    while queue:
        task_name = queue.pop(0)

        if task_name in reachable:
            continue  # Already processed

        reachable.add(task_name)

        # Get task and process its dependencies
        task = tasks.get(task_name)
        if task is None:
            # Task not found - will be caught during graph construction
            continue

        # Add dependency task names to queue
        for dep_spec in task.deps:
            # Extract task name from dependency specification
            if isinstance(dep_spec, str):
                dep_name = dep_spec
            elif isinstance(dep_spec, dict) and len(dep_spec) == 1:
                dep_name = next(iter(dep_spec.keys()))
            else:
                # Invalid format - will be caught during graph construction
                continue

            if dep_name not in reachable:
                queue.append(dep_name)

    return reachable


def collect_reachable_variables(
    tasks: dict[str, Task],
    runners: dict[str, Runner],
    reachable_task_names: set[str],
) -> set[str]:
    """
    Extract variable names used by reachable tasks.

    Searches for {{ var.* }} placeholders in task and runner definitions to determine
    which variables are actually needed for execution.

    Args:
    tasks: Dictionary mapping task names to Task objects
    runners: Dictionary mapping runner names to Runner objects
    reachable_task_names: Set of task names that will be executed

    Returns:
    Set of variable names referenced by reachable tasks

    Example:
    >>> task = Task("build", cmd="echo {{ var.version }}")
    >>> collect_reachable_variables({"build": task}, {"build"})
    {"version"}
    """
    import re

    variables = set()

    for task_name in reachable_task_names:
        task = tasks.get(task_name)
        if task is None:
            continue

        # Search in command
        if task.cmd:
            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(task.cmd):
                variables.add(match.group(1))

        # Search in description
        if task.desc:
            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(task.desc):
                variables.add(match.group(1))

        # Search in working_dir
        if task.working_dir:
            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(task.working_dir):
                variables.add(match.group(1))

        # Search in inputs
        if task.inputs:
            for input_pattern in task.inputs:
                if isinstance(input_pattern, str):
                    for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(input_pattern):
                        variables.add(match.group(1))
                elif isinstance(input_pattern, dict):
                    # Named input - check the path value
                    for input_path in input_pattern.values():
                        if isinstance(input_path, str):
                            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(input_path):
                                variables.add(match.group(1))

        # Search in outputs
        if task.outputs:
            for output_pattern in task.outputs:
                if isinstance(output_pattern, str):
                    for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(output_pattern):
                        variables.add(match.group(1))
                elif isinstance(output_pattern, dict):
                    # Named output - check the path value
                    for output_path in output_pattern.values():
                        if isinstance(output_path, str):
                            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(output_path):
                                variables.add(match.group(1))

        # Search in argument defaults
        if task.args:
            for arg_spec in task.args:
                if isinstance(arg_spec, dict):
                    for arg_dict in arg_spec.values():
                        if isinstance(arg_dict, dict) and "default" in arg_dict:
                            default = arg_dict["default"]
                            if isinstance(default, str):
                                for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(default):
                                    variables.add(match.group(1))

        # Search in dependency argument templates
        if task.deps:
            for dep_spec in task.deps:
                if isinstance(dep_spec, dict):
                    for arg_spec in dep_spec.values():
                        # Positional args (list)
                        if isinstance(arg_spec, list):
                            for val in arg_spec:
                                if isinstance(val, str):
                                    for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(val):
                                        variables.add(match.group(1))
                        # Named args (dict)
                        elif isinstance(arg_spec, dict):
                            for val in arg_spec.values():
                                if isinstance(val, str):
                                    for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(val):
                                        variables.add(match.group(1))

        if task.run_in:
            if task.run_in in runners:
                env = runners[task.run_in]

                if env.dockerfile and env.dockerfile != "":
                    for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(env.dockerfile):
                        variables.add(match.group(1))

                    if env.context != "":
                        for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(env.context):
                            variables.add(match.group(1))

                    if 0 != len(env.volumes):
                        for v in env.volumes:
                            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(v):
                                variables.add(match.group(1))

                    if 0 != len(env.ports):
                        for p in env.ports:
                            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(p):
                                variables.add(match.group(1))

                    if 0 != len(env.env_vars):
                        for k, v in env.env_vars.items():
                            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(v):
                                variables.add(match.group(1))

                    if env.working_dir != "":
                        for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(env.working_dir):
                            variables.add(match.group(1))

                    if 0 != len(env.extra_args):
                        for e in env.extra_args:
                            for match in VAR_REFERENCE_EXTRACT_PATTERN.finditer(e):
                                variables.add(match.group(1))

    return variables


def parse_recipe(
    recipe_path: Path, project_root: Path | None = None, root_task: str | None = None
) -> Recipe:
    """
    Parse a recipe file and handle imports recursively.

    This function now implements lazy variable evaluation: if root_task is provided,
    only variables reachable from that task will be evaluated. This provides significant
    performance and security benefits for recipes with many variables.

    Args:
    recipe_path: Path to the main recipe file
    project_root: Optional project root directory. If not provided, uses recipe file's parent directory.
    When using --tasks option, this should be the current working directory.
    root_task: Optional root task for lazy variable evaluation. If provided, only variables
    used by tasks reachable from root_task will be evaluated (optimization).
    If None, all variables will be evaluated (for --list command compatibility).

    Returns:
    Recipe object with all tasks (including recursively imported tasks) and evaluated variables

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
    # Variables are NOT evaluated here (lazy evaluation)
    tasks, runners, default_runner, raw_variables, yaml_data, name_errors = _parse_file_with_env(
        recipe_path, namespace=None, project_root=project_root
    )

    # Create recipe with raw (unevaluated) variables
    recipe = Recipe(
        tasks=tasks,
        project_root=project_root,
        recipe_path=recipe_path,
        runners=runners,
        default_runner=default_runner,
        variables={},  # Empty initially (deprecated field)
        raw_variables=raw_variables,
        evaluated_variables={},  # Empty initially
        _variables_evaluated=False,
        _original_yaml_data=yaml_data,
        _name_errors=name_errors,
    )

    # Trigger lazy variable evaluation
    # If root_task is provided: evaluate only reachable variables
    # If root_task is None: evaluate all variables (for --list)
    recipe.evaluate_variables(root_task)

    return recipe


def _parse_file(
    file_path: Path,
    namespace: str | None,
    project_root: Path,
    import_stack: list[Path] | None = None,
    blanket_runner: str = "",
) -> ParsedFileResult:
    """
    Parse a single YAML file and return tasks, recursively processing imports.

    Args:
    file_path: Path to YAML file
    namespace: Optional namespace prefix for tasks
    project_root: Root directory of the project
    import_stack: Stack of files being imported (for circular detection)
    blanket_runner: Optional runner name to apply to all non-pinned tasks in this file

    Returns:
    ParsedFileResult containing tasks, runners, and raw variables

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
    runners: dict[str, Runner] = {}
    raw_variables: dict[str, Any] = {}
    name_errors: dict[str, str] = {}
    # TODO: Understand why this is not used.
    # file_dir = file_path.parent

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
            child_run_in = import_spec.get("run_in", "")

            # Track this namespace as a local import
            local_import_namespaces.add(child_namespace)

            # Build full namespace chain
            full_namespace = (
                f"{namespace}.{child_namespace}" if namespace else child_namespace
            )

            # Resolve import path relative to current file's directory
            child_path = file_path.parent / child_file
            if not child_path.exists():
                raise FileNotFoundError(f"Import file not found: {child_path}")

            # Recursively process with namespace chain and import stack
            nested_result = _parse_file(
                child_path,
                full_namespace,
                project_root,
                import_stack.copy(),  # Pass copy to avoid shared mutation
                child_run_in,  # Pass blanket runner to imported file
            )

            tasks.update(nested_result.tasks)

            # Selective runner import: Only import runners referenced by pinned tasks
            #
            # Rationale: This allows root files to provide blanket runner overrides
            # for non-pinned imported tasks without namespace pollution. Tasks with
            # pin_runner=true explicitly opt-in to bringing their runners along.
            # Non-pinned tasks will use the blanket runner specified in run_in import option.
            #
            # Example:
            #   imports:
            #     - file: build.yaml
            #       as: build
            #       run_in: docker  # Blanket override for non-pinned tasks
            #
            # If build.yaml has:
            #   - task1 with run_in: shell, pin_runner: true  -> Uses build.shell (imported)
            #   - task2 with no run_in                        -> Uses docker (blanket override)
            pinned_runner_names = {
                task.run_in
                for task in nested_result.tasks.values()
                if task.pin_runner and task.run_in
            }
            # Selective import of runners (Step 3.2)
            # Import only runners that are referenced by pinned tasks.
            # Note: Runners in nested_result are already namespaced by the recursive parse,
            # so we don't add another namespace prefix here.
            # Example: runner "shell" in build.yaml is already "build.shell" in nested_result
            runners_to_import = {
                name: runner
                for name, runner in nested_result.runners.items()
                if name in pinned_runner_names
            }
            runners.update(runners_to_import)

            raw_variables.update(nested_result.raw_variables)
            name_errors.update(nested_result.name_errors)

    # Validate top-level keys (only imports, runners, tasks, and variables are allowed)
    valid_top_level_keys = {"imports", "runners", "tasks", "variables"}

    # Check if tasks key is missing when there appear to be task definitions at root
    # Do this BEFORE checking for unknown keys, to provide better error message
    if "tasks" not in data and data:
        # Check if there are potential task definitions at root level
        potential_tasks = [
            k
            for k, v in data.items()
            if isinstance(v, dict) and k not in valid_top_level_keys
        ]

        if potential_tasks:
            raise ValueError(
                f"Invalid recipe format in {file_path}\n\n"
                f"Task definitions must be under a top-level 'tasks:' key.\n\n"
                f"Found these keys at root level: {', '.join(potential_tasks)}\n\n"
                f"Did you mean:\n\n"
                f"tasks:\n"
                + "\n".join(f"  {k}:" for k in potential_tasks)
                + "\n    cmd: ...\n\n"
                f"Valid top-level keys are: {', '.join(sorted(valid_top_level_keys))}"
            )

    # Now check for other invalid top-level keys (non-dict values)
    invalid_keys = set(data.keys()) - valid_top_level_keys
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

        task_name_error = _validate_local_item_name(task_name, "Task")
        if task_name_error:
            raise ValueError(task_name_error)

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
                if isinstance(dep, str):
                    # Simple string dependency
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
                elif isinstance(dep, dict):
                    # Dict dependency with args - rewrite the task name key
                    rewritten_dep = {}
                    for t_name, args in dep.items():
                        if "." not in t_name:
                            # Simple name - prefix it
                            rewritten_dep[f"{namespace}.{t_name}"] = args
                        else:
                            # Check if it starts with a local import namespace
                            dep_root = t_name.split(".", 1)[0]
                            if dep_root in local_import_namespaces:
                                # Local import reference - prefix it
                                rewritten_dep[f"{namespace}.{t_name}"] = args
                            else:
                                # External reference - keep as-is
                                rewritten_dep[t_name] = args
                    rewritten_deps.append(rewritten_dep)
                else:
                    # Unknown type - keep as-is
                    rewritten_deps.append(dep)
            deps = rewritten_deps

        # Rewrite run_in with namespace prefix for imported tasks
        run_in = task_data.get("run_in", "")
        if namespace and run_in:
            run_in = f"{namespace}.{run_in}"

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
            run_in=run_in,
            private=task_data.get("private", False),
            pin_runner=task_data.get("pin_runner", False),
            task_output=task_data.get("task_output", None),
        )

        # Apply blanket runner to non-pinned tasks from imports
        if blanket_runner and not task.pin_runner and not task.run_in:
            task.run_in = blanket_runner

        # Rewrite {{ var.* }} references in imported tasks
        if namespace:
            _rewrite_task_variable_references(task, namespace)

        # Check for case-sensitive argument collisions
        if task.args:
            _check_case_sensitive_arg_collisions(task.args, full_name)

        tasks[full_name] = task

    # Parse runners and variables from imported files (namespace is set) and apply namespace prefix
    # Root file runners/variables are handled by _parse_file_with_env, not here
    if namespace:
        local_runners, _ = _parse_runners_from_data(data, project_root)
        for runner_name, runner in local_runners.items():
            full_runner_name = f"{namespace}.{runner_name}"
            error = _validate_local_item_name(runner_name, "Runner")
            if error:
                name_errors[full_runner_name] = error
            runner.name = full_runner_name
            _rewrite_runner_variable_references(runner, namespace)
            runners[full_runner_name] = runner

        local_vars = data.get("variables", {})
        if isinstance(local_vars, dict):
            for var_name, var_value in local_vars.items():
                full_var_name = f"{namespace}.{var_name}"
                error = _validate_local_item_name(var_name, "Variable")
                if error:
                    name_errors[full_var_name] = error
                raw_variables[full_var_name] = _rewrite_variable_references_in_raw_value(
                    var_value, namespace
                )

    # Remove current file from stack
    import_stack.pop()

    return ParsedFileResult(tasks=tasks, runners=runners, raw_variables=raw_variables, name_errors=name_errors)


def _check_case_sensitive_arg_collisions(args: list[str], task_name: str) -> None:
    """
    Check for exported arguments that differ only in case.

    On Unix systems, environment variables are case-sensitive, but having
    args that differ only in case (e.g., $Server and $server) can be confusing.
    This function emits a warning if such collisions are detected.

    Args:
    args: List of argument specifications
    task_name: Name of the task (for warning message)
    """
    import sys

    # Parse all exported arg names
    exported_names = []
    for arg_spec in args:
        parsed = parse_arg_spec(arg_spec)
        if parsed.is_exported:
            exported_names.append(parsed.name)

    # Check for case collisions
    seen_lower = {}
    for name in exported_names:
        lower_name = name.lower()
        if lower_name in seen_lower:
            # Found a collision
            other_name = seen_lower[lower_name]
            if name != other_name:  # Only warn if actual case differs
                print(
                    f"Warning: Task '{task_name}' has exported arguments that differ only in case: "
                    f"${other_name} and ${name}. "
                    f"This may be confusing on case-sensitive systems.",
                    file=sys.stderr,
                )
        else:
            seen_lower[lower_name] = name


def parse_arg_spec(arg_spec: str | dict) -> ArgSpec:
    """
    Parse argument specification from YAML.

    Supports both string format and dictionary format:

    String format (simple names only):
    - Simple name: "argname"
    - Exported (becomes env var): "$argname"

    Dictionary format:
    - argname: { default: "value" }
    - argname: { type: int, default: 42 }
    - argname: { type: int, min: 1, max: 100 }
    - argname: { type: str, choices: ["dev", "staging", "prod"] }
    - $argname: { default: "value" }  # Exported (type not allowed)

    Args:
    arg_spec: Argument specification (string or dict with single key)

    Returns:
    ArgSpec object containing parsed argument information

    Examples:
    >>> parse_arg_spec("environment")
    ArgSpec(name='environment', arg_type='str', default=None, is_exported=False, min_val=None, max_val=None, choices=None)
    >>> parse_arg_spec({"key2": {"default": "foo"}})
    ArgSpec(name='key2', arg_type='str', default='foo', is_exported=False, min_val=None, max_val=None, choices=None)
    >>> parse_arg_spec({"key3": {"type": "int", "default": 42}})
    ArgSpec(name='key3', arg_type='int', default='42', is_exported=False, min_val=None, max_val=None, choices=None)
    >>> parse_arg_spec({"replicas": {"type": "int", "min": 1, "max": 100}})
    ArgSpec(name='replicas', arg_type='int', default=None, is_exported=False, min_val=1, max_val=100, choices=None)
    >>> parse_arg_spec({"env": {"type": "str", "choices": ["dev", "prod"]}})
    ArgSpec(name='env', arg_type='str', default=None, is_exported=False, min_val=None, max_val=None, choices=['dev', 'prod'])

    Raises:
    ValueError: If argument specification is invalid
    """
    # Handle dictionary format: { argname: { type: ..., default: ... } }
    if isinstance(arg_spec, dict):
        if len(arg_spec) != 1:
            raise ValueError(
                f"Argument dictionary must have exactly one key (the argument name), got: {list(arg_spec.keys())}"
            )

        # Extract the argument name and its configuration
        arg_name, config = next(iter(arg_spec.items()))

        # Check if argument is exported (name starts with $)
        is_exported = arg_name.startswith("$")
        if is_exported:
            arg_name = arg_name[1:]  # Remove $ prefix

        # Validate argument name
        if not arg_name or not isinstance(arg_name, str):
            raise ValueError(
                f"Argument name must be a non-empty string, got: {arg_name!r}"
            )

        # Config must be a dictionary
        if not isinstance(config, dict):
            raise ValueError(
                f"Argument '{arg_name}' configuration must be a dictionary, got: {type(config).__name__}"
            )

        return _parse_arg_dict(arg_name, config, is_exported)

    # Handle string format
    # Check if argument is exported (starts with $)
    is_exported = arg_spec.startswith("$")
    if is_exported:
        arg_spec = arg_spec[1:]  # Remove $ prefix

    # String format only supports simple names (no = or :)
    if "=" in arg_spec or ":" in arg_spec:
        raise ValueError(
            f"Invalid argument syntax: {'$' if is_exported else ''}{arg_spec}\n\n"
            f"String format only supports simple argument names.\n"
            f"Use YAML dict format for type annotations, defaults, or constraints:\n"
            f"  args:\n"
            f"    - {'$' if is_exported else ''}{arg_spec.split('=')[0].split(':')[0]}: {{ default: value }}"
        )

    name = arg_spec
    arg_type = "str"

    # String format doesn't support min/max/choices/defaults
    return ArgSpec(
        name=name,
        arg_type=arg_type,
        default=None,
        is_exported=is_exported,
        min_val=None,
        max_val=None,
        choices=None,
    )


def _parse_arg_dict(arg_name: str, config: dict, is_exported: bool) -> ArgSpec:
    """
    Parse argument specification from dictionary format.

    Args:
    arg_name: Name of the argument
    config: Dictionary with optional keys: type, default, min, max, choices
    is_exported: Whether argument should be exported to environment

    Returns:
    ArgSpec object containing the parsed argument specification

    Raises:
    ValueError: If dictionary format is invalid
    """
    # Validate dictionary keys
    valid_keys = {"type", "default", "min", "max", "choices"}
    invalid_keys = set(config.keys()) - valid_keys
    if invalid_keys:
        raise ValueError(
            f"Invalid keys in argument '{arg_name}' configuration: {', '.join(sorted(invalid_keys))}\n"
            f"Valid keys are: {', '.join(sorted(valid_keys))}"
        )

    # Extract values
    arg_type = config.get("type")
    default = config.get("default")
    min_val = config.get("min")
    max_val = config.get("max")
    choices = config.get("choices")

    # Track if an explicit type was provided (for validation later)
    explicit_type = arg_type

    # Exported arguments cannot have type annotations
    if is_exported and arg_type is not None:
        raise ValueError(
            f"Type annotations not allowed on exported argument '${arg_name}'\n"
            f"Exported arguments are always strings. Remove the 'type' field"
        )

    # Exported arguments must have string defaults (if any default is provided)
    if is_exported and default is not None and not isinstance(default, str):
        raise ValueError(
            f"Exported argument '${arg_name}' must have a string default value.\n"
            f"Got: {default!r} (type: {type(default).__name__})\n"
            f"Exported arguments become environment variables, which are always strings.\n"
            f'Use a quoted string: ${arg_name}: {{ default: "{default}" }}'
        )

    # Validate choices
    if choices is not None:
        # Validate choices is a list
        if not isinstance(choices, list):
            raise ValueError(f"Argument '{arg_name}': choices must be a list")

        # Validate choices is not empty
        if len(choices) == 0:
            raise ValueError(f"Argument '{arg_name}': choices list cannot be empty")

        # Check for mutual exclusivity with min/max
        if min_val is not None or max_val is not None:
            raise ValueError(
                f"Argument '{arg_name}': choices and min/max are mutually exclusive.\n"
                f"Use either choices for discrete values or min/max for ranges, not both."
            )

    # Infer type from default, min, max, or choices if type not specified
    if arg_type is None:
        # Collect all values that can help infer type
        inferred_types = []

        if default is not None:
            inferred_types.append(("default", _infer_variable_type(default)))
        if min_val is not None:
            inferred_types.append(("min", _infer_variable_type(min_val)))
        if max_val is not None:
            inferred_types.append(("max", _infer_variable_type(max_val)))
        if choices is not None and len(choices) > 0:
            inferred_types.append(("choices[0]", _infer_variable_type(choices[0])))

        if inferred_types:
            # Check all inferred types are consistent
            first_name, first_type = inferred_types[0]
            for value_name, value_type in inferred_types[1:]:
                if value_type != first_type:
                    # Build error message showing the conflicting types
                    type_info = ", ".join(
                        [f"{name}={vtype}" for name, vtype in inferred_types]
                    )
                    raise ValueError(
                        f"Argument '{arg_name}': inconsistent types inferred from min, max, and default.\n"
                        f"All values must have the same type.\n"
                        f"Found: {type_info}"
                    )

            # All types are consistent, use the inferred type
            arg_type = first_type
        else:
            # No values to infer from, default to string
            arg_type = "str"
    else:
        # Explicit type was provided - validate that default matches it
        # (min/max validation happens later, after the min/max numeric check)
        if default is not None:
            default_type = _infer_variable_type(default)
            if default_type != explicit_type:
                raise ValueError(
                    f"Default value for argument '{arg_name}' is incompatible with type '{explicit_type}': "
                    f"default has type '{default_type}'"
                )

    # Validate min/max are only used with numeric types
    if (min_val is not None or max_val is not None) and arg_type not in (
        "int",
        "float",
    ):
        raise ValueError(
            f"Argument '{arg_name}': min/max constraints are only supported for 'int' and 'float' types, "
            f"not '{arg_type}'"
        )

    # If explicit type was provided, validate min/max match that type
    if explicit_type is not None and arg_type in ("int", "float"):
        type_mismatches = []
        if min_val is not None:
            min_type = _infer_variable_type(min_val)
            if min_type != explicit_type:
                type_mismatches.append(f"min value has type '{min_type}'")
        if max_val is not None:
            max_type = _infer_variable_type(max_val)
            if max_type != explicit_type:
                type_mismatches.append(f"max value has type '{max_type}'")

        if type_mismatches:
            raise ValueError(
                f"Argument '{arg_name}': explicit type '{explicit_type}' does not match value types.\n"
                + "\n".join([f"  - {mismatch}" for mismatch in type_mismatches])
            )

    # Validate min <= max
    if min_val is not None and max_val is not None:
        if min_val > max_val:
            raise ValueError(
                f"Argument '{arg_name}': min ({min_val}) must be less than or equal to max ({max_val})"
            )

    # Validate type name and get validator
    try:
        validator = get_click_type(arg_type)
    except ValueError:
        raise ValueError(
            f"Unknown type in argument '{arg_name}': {arg_type}\n"
            f"Supported types: str, int, float, bool, path, datetime, ip, ipv4, ipv6, email, hostname"
        )

    # Validate choices
    if choices is not None:
        # Boolean types cannot have choices
        if arg_type == "bool":
            raise ValueError(
                f"Argument '{arg_name}': boolean types cannot have choices.\n"
                f"Boolean values are already limited to true/false."
            )

        # Validate all choices are the same type
        if len(choices) > 0:
            first_choice_type = _infer_variable_type(choices[0])

            # If explicit type was provided, validate choices match it
            if explicit_type is not None and first_choice_type != explicit_type:
                raise ValueError(
                    f"Argument '{arg_name}': choice values do not match explicit type '{explicit_type}'.\n"
                    f"First choice has type '{first_choice_type}'"
                )

            # Check all choices have the same type
            for i, choice in enumerate(choices[1:], start=1):
                choice_type = _infer_variable_type(choice)
                if choice_type != first_choice_type:
                    raise ValueError(
                        f"Argument '{arg_name}': all choice values must have the same type.\n"
                        f"First choice has type '{first_choice_type}', but choice at index {i} has type '{choice_type}'"
                    )

            # Validate all choices are valid for the type
            for i, choice in enumerate(choices):
                try:
                    validator.convert(choice, None, None)
                except Exception as e:
                    raise ValueError(
                        f"Argument '{arg_name}': choice at index {i} ({choice!r}) is invalid for type '{arg_type}': {e}"
                    )

    # Validate and convert default value
    if default is not None:
        # Validate that default is compatible with the declared type
        if arg_type != "str":
            # Validate that the default value is compatible with the type
            try:
                # Use the validator we already retrieved
                converted_default = validator.convert(default, None, None)
            except Exception as e:
                raise ValueError(
                    f"Default value for argument '{arg_name}' is incompatible with type '{arg_type}': {e}"
                )

            # Validate default is within min/max range
            if min_val is not None and converted_default < min_val:
                raise ValueError(
                    f"Default value for argument '{arg_name}' ({default}) is less than min ({min_val})"
                )
            if max_val is not None and converted_default > max_val:
                raise ValueError(
                    f"Default value for argument '{arg_name}' ({default}) is greater than max ({max_val})"
                )

            # Validate default is in choices list
            if choices is not None and converted_default not in choices:
                raise ValueError(
                    f"Default value for argument '{arg_name}' ({default}) is not in the choices list.\n"
                    f"Valid choices: {choices}"
                )

            # After validation, convert to string for storage
            default_str = str(default)
        else:
            # For string type, validate default is in choices
            if choices is not None and default not in choices:
                raise ValueError(
                    f"Default value for argument '{arg_name}' ({default}) is not in the choices list.\n"
                    f"Valid choices: {choices}"
                )
            default_str = str(default)
    else:
        # None remains None (not the string "None")
        default_str = None

    return ArgSpec(
        name=arg_name,
        arg_type=arg_type,
        default=default_str,
        is_exported=is_exported,
        min_val=min_val,
        max_val=max_val,
        choices=choices,
    )


def parse_dependency_spec(
    dep_spec: str | dict[str, Any], recipe: Recipe
) -> DependencyInvocation:
    """
    Parse a dependency specification into a DependencyInvocation.

    Supports three forms:
    1. Simple string: "task_name" -> DependencyInvocation(task_name, None)
    2. Positional args: {"task_name": [arg1, arg2]} -> DependencyInvocation(task_name, {name1: arg1, name2: arg2})
    3. Named args: {"task_name": {arg1: val1}} -> DependencyInvocation(task_name, {arg1: val1})

    Args:
    dep_spec: Dependency specification (string or dict)
    recipe: Recipe containing task definitions (for arg normalization)

    Returns:
    DependencyInvocation object with normalized args

    Raises:
    ValueError: If dependency specification is invalid
    """
    # Simple string case
    if isinstance(dep_spec, str):
        return DependencyInvocation(task_name=dep_spec, args=None)

    # Dictionary case
    if not isinstance(dep_spec, dict):
        raise ValueError(
            f"Dependency must be a string or dictionary, got: {type(dep_spec).__name__}"
        )

    # Validate dict has exactly one key
    if len(dep_spec) != 1:
        raise ValueError(
            f"Dependency dictionary must have exactly one key (the task name), got: {list(dep_spec.keys())}"
        )

    task_name, arg_spec = next(iter(dep_spec.items()))

    # Validate task name
    if not isinstance(task_name, str) or not task_name:
        raise ValueError(
            f"Dependency task name must be a non-empty string, got: {task_name!r}"
        )

    # Check for empty list (explicitly disallowed)
    if isinstance(arg_spec, list) and len(arg_spec) == 0:
        raise ValueError(
            f"Empty argument list for dependency '{task_name}' is not allowed.\n"
            f"Use simple string form instead: '{task_name}'"
        )

    # Positional args (list)
    if isinstance(arg_spec, list):
        return _parse_positional_dependency_args(task_name, arg_spec, recipe)

    # Named args (dict)
    if isinstance(arg_spec, dict):
        return _parse_named_dependency_args(task_name, arg_spec, recipe)

    # Invalid type
    raise ValueError(
        f"Dependency arguments for '{task_name}' must be a list (positional) or dict (named), "
        f"got: {type(arg_spec).__name__}"
    )


def _get_validated_task(task_name: str, recipe: Recipe) -> Task:
    """
    Get and validate that a task exists in the recipe.

    Args:
    task_name: Name of the task to retrieve
    recipe: Recipe containing task definitions

    Returns:
    The validated Task object

    Raises:
    ValueError: If task is not found
    """
    task = recipe.get_task(task_name)
    if task is None:
        raise ValueError(f"Dependency task not found: {task_name}")
    return task


def _parse_positional_dependency_args(
    task_name: str, args_list: list[Any], recipe: Recipe
) -> DependencyInvocation:
    """
    Parse positional dependency arguments.

    Args:
    task_name: Name of the dependency task
    args_list: List of positional argument values
    recipe: Recipe containing task definitions

    Returns:
    DependencyInvocation with normalized named args

    Raises:
    ValueError: If validation fails
    """
    # Get the task to validate against
    task = _get_validated_task(task_name, recipe)

    # Parse task's arg specs
    if not task.args:
        raise ValueError(
            f"Task '{task_name}' takes no arguments, but {len(args_list)} were provided"
        )

    parsed_specs = [parse_arg_spec(spec) for spec in task.args]

    # Check positional count doesn't exceed task's arg count
    if len(args_list) > len(parsed_specs):
        raise ValueError(
            f"Task '{task_name}' takes {len(parsed_specs)} arguments, got {len(args_list)}"
        )

    # Map positional args to names with type conversion
    args_dict = {}
    for i, value in enumerate(args_list):
        spec = parsed_specs[i]
        if isinstance(value, str):
            # Convert string values using type validator
            click_type = get_click_type(
                spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
            )
            args_dict[spec.name] = click_type.convert(value, None, None)
        else:
            # Value is already typed (e.g., bool, int from YAML)
            args_dict[spec.name] = value

    # Fill in defaults for remaining args
    for i in range(len(args_list), len(parsed_specs)):
        spec = parsed_specs[i]
        if spec.default is not None:
            # Defaults in task specs are always strings, convert them
            click_type = get_click_type(
                spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
            )
            args_dict[spec.name] = click_type.convert(spec.default, None, None)
        else:
            raise ValueError(
                f"Task '{task_name}' requires argument '{spec.name}' (no default provided)"
            )

    return DependencyInvocation(task_name=task_name, args=args_dict)


def _parse_named_dependency_args(
    task_name: str, args_dict: dict[str, Any], recipe: Recipe
) -> DependencyInvocation:
    """
    Parse named dependency arguments.

    Args:
    task_name: Name of the dependency task
    args_dict: Dictionary of argument names to values
    recipe: Recipe containing task definitions

    Returns:
    DependencyInvocation with normalized args (defaults filled)

    Raises:
    ValueError: If validation fails
    """
    # Get the task to validate against
    task = _get_validated_task(task_name, recipe)

    # Parse task's arg specs
    if not task.args:
        if args_dict:
            raise ValueError(
                f"Task '{task_name}' takes no arguments, but {len(args_dict)} were provided"
            )
        return DependencyInvocation(task_name=task_name, args={})

    parsed_specs = [parse_arg_spec(spec) for spec in task.args]
    spec_map = {spec.name: spec for spec in parsed_specs}

    # Validate all provided arg names exist
    for arg_name in args_dict:
        if arg_name not in spec_map:
            raise ValueError(f"Task '{task_name}' has no argument named '{arg_name}'")

    # Build normalized args dict with defaults
    normalized_args = {}
    for spec in parsed_specs:
        if spec.name in args_dict:
            # Use provided value with type conversion (only convert strings)
            value = args_dict[spec.name]
            if isinstance(value, str):
                click_type = get_click_type(
                    spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
                )
                normalized_args[spec.name] = click_type.convert(value, None, None)
            else:
                # Value is already typed (e.g., bool, int from YAML)
                normalized_args[spec.name] = value
        elif spec.default is not None:
            # Use default value (defaults are always strings in task specs)
            click_type = get_click_type(
                spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
            )
            normalized_args[spec.name] = click_type.convert(spec.default, None, None)
        else:
            # Required arg not provided
            raise ValueError(
                f"Task '{task_name}' requires argument '{spec.name}' (no default provided)"
            )

    return DependencyInvocation(task_name=task_name, args=normalized_args)


def get_recipe(
    logger: Logger, recipe_file: Optional[str] = None, root_task: Optional[str] = None
) -> Optional[Recipe]:
    """
    Get parsed recipe or None if not found.

    Args:
    logger_fn: Logger function for output
    recipe_file: Optional path to recipe file. If not provided, searches for recipe file.
    root_task: Optional root task for lazy variable evaluation. If provided, only variables
    reachable from this task will be evaluated (performance optimization).
    """
    if recipe_file:
        recipe_path = Path(recipe_file)
        if not recipe_path.exists():
            logger.error(f"[red]Recipe file not found: {recipe_file}[/red]")
            raise typer.Exit(1)
        # When explicitly specified, project root is current working directory
        project_root = Path.cwd()
    else:
        try:
            recipe_path = find_recipe_file()
            if recipe_path is None:
                return None
        except ValueError as e:
            # Multiple recipe files found
            logger.error(f"[red]{e}[/red]")
            raise typer.Exit(1)
        # When auto-discovered, project root is recipe file's parent
        project_root = None

    try:
        return parse_recipe(recipe_path, project_root, root_task)
    except Exception as e:
        logger.error(f"[red]Error parsing recipe: {e}[/red]")
        raise typer.Exit(1)


def parse_task_args(
    logger: Logger, arg_specs: list[str], arg_values: list[str]
) -> dict[str, Any]:
    """
    Parse and validate task arguments from command line values.

    Args:
    logger: Logger interface for output
    arg_specs: Task argument specifications with types and defaults
    arg_values: Raw argument values from command line (positional or named)

    Returns:
    Dictionary mapping argument names to typed, validated values

    Raises:
    typer.Exit: If arguments are invalid, missing, or unknown

    """
    if not arg_specs:
        if arg_values:
            logger.error("[red]Task does not accept arguments[/red]")
            raise typer.Exit(1)
        return {}

    parsed_specs = []
    for spec in arg_specs:
        parsed = parse_arg_spec(spec)
        parsed_specs.append(parsed)

    args_dict = {}
    positional_index = 0

    for i, value_str in enumerate(arg_values):
        # Check if it's a named argument (name=value)
        if "=" in value_str:
            arg_name, arg_value = value_str.split("=", 1)
            # Find the spec for this argument
            spec = next((s for s in parsed_specs if s.name == arg_name), None)
            if spec is None:
                logger.error(f"[red]Unknown argument: {arg_name}[/red]")
                raise typer.Exit(1)
        else:
            # Positional argument
            if positional_index >= len(parsed_specs):
                logger.error("[red]Too many arguments[/red]")
                raise typer.Exit(1)
            spec = parsed_specs[positional_index]
            arg_value = value_str
            positional_index += 1

        # Convert value to appropriate type (exported args are always strings)
        try:
            click_type = get_click_type(
                spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
            )
            converted_value = click_type.convert(arg_value, None, None)

            # Validate choices after type conversion
            if spec.choices is not None and converted_value not in spec.choices:
                logger.error(
                    f"[red]Invalid value for {spec.name}: {converted_value!r}[/red]",
                )
                logger.info(
                    f"Valid choices: {', '.join(repr(c) for c in spec.choices)}",
                )
                raise typer.Exit(1)

            args_dict[spec.name] = converted_value
        except typer.Exit:
            raise  # Re-raise typer.Exit without wrapping
        except Exception as e:
            logger.error(f"[red]Invalid value for {spec.name}: {e}[/red]")
            raise typer.Exit(1)

    # Fill in defaults for missing arguments
    for spec in parsed_specs:
        if spec.name not in args_dict:
            if spec.default is not None:
                try:
                    click_type = get_click_type(
                        spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
                    )
                    args_dict[spec.name] = click_type.convert(spec.default, None, None)
                except Exception as e:
                    logger.error(
                        f"[red]Invalid default value for {spec.name}: {e}[/red]",
                    )
                    raise typer.Exit(1)
            else:
                logger.error(f"[red]Missing required argument: {spec.name}[/red]")
                raise typer.Exit(1)

    return args_dict
