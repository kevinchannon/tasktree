"""Placeholder substitution for variables, arguments, and environment variables.

This module provides functions to substitute {{ var.name }}, {{ arg.name }},
and {{ env.NAME }} placeholders with their corresponding values.
"""

import re
from random import choice
from typing import Any


# Pattern matches: {{ prefix.name }} with optional whitespace
# Groups: (1) prefix (var|arg|env|tt), (2) name (identifier)
PLACEHOLDER_PATTERN = re.compile(
    r'\{\{\s*(var|arg|env|tt)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
)

# Pattern matches: {{ dep.task_name.outputs.output_name }} with optional whitespace
# Groups: (1) task_name (can include dots for namespacing), (2) output_name (identifier)
DEP_OUTPUT_PATTERN = re.compile(
    r'\{\{\s*dep\.([a-zA-Z_][a-zA-Z0-9_.-]*)\.outputs\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
)

# Pattern matches: {{ self.(inputs|outputs).name }} with optional whitespace
# Groups: (1) field (inputs|outputs), (2) name (identifier)
SELF_REFERENCE_PATTERN = re.compile(
    r'\{\{\s*self\.(inputs|outputs)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
)


def substitute_variables(text: str | dict[str, Any], variables: dict[str, str]) -> str | dict[str, Any]:
    """Substitute {{ var.name }} placeholders with variable values.

    Args:
        text: Text containing {{ var.name }} placeholders, or an argument dict with elements to be substituted
        variables: Dictionary mapping variable names to their string values

    Returns:
        Text with all {{ var.name }} placeholders replaced

    Raises:
        ValueError: If a referenced variable is not defined
    """
    if isinstance(text, dict):
        # The dict will only contain a single key, the value of this key should also be a dictionary, which contains
        # the actual details of the argument.
        assert len(text.keys()) == 1

        for arg_name in text.keys():
            # Pull out and substitute the individual fields of an argument one at a time
            for field in  [ "default", "min", "max" ]:
                if field in text[arg_name]:
                    text[arg_name][field] = substitute_variables(text[arg_name][field], variables)

            # choices is a list of things
            if "choices" in text[arg_name]:
                text[arg_name]["choices"] = [substitute_variables(c, variables) for c in text[arg_name]["choices"]]

            return text
        else:
            raise ValueError("Empty arg dictionary")
    else:
        # If not a string (e.g., int, float, bool, None), return unchanged
        # This handles cases like: default: 5, min: 0, choices: [1, 2, 3]
        if not isinstance(text, str):
            return text

        def replace_match(match: re.Match) -> str:
            prefix = match.group(1)
            name = match.group(2)

            # Only substitute var: placeholders
            if prefix != "var":
                return match.group(0)  # Return unchanged

            if name not in variables:
                raise ValueError(
                    f"Variable '{name}' is not defined. "
                    f"Variables must be defined before use."
                )

            return variables[name]

        return PLACEHOLDER_PATTERN.sub(replace_match, text)


def substitute_arguments(text: str, args: dict[str, Any], exported_args: set[str] | None = None) -> str:
    """Substitute {{ arg.name }} placeholders with argument values.

    Args:
        text: Text containing {{ arg.name }} placeholders
        args: Dictionary mapping argument names to their values
        exported_args: Set of argument names that are exported (not available for substitution)

    Returns:
        Text with all {{ arg.name }} placeholders replaced

    Raises:
        ValueError: If a referenced argument is not provided or is exported
    """
    # Use empty set if None for cleaner handling
    exported_args = exported_args or set()

    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        name = match.group(2)

        # Only substitute arg: placeholders
        if prefix != "arg":
            return match.group(0)  # Return unchanged

        # Check if argument is exported (not available for substitution)
        if name in exported_args:
            raise ValueError(
                f"Argument '{name}' is exported (defined as ${name}) and cannot be used in template substitution\n"
                f"Template: {{{{ arg.{name} }}}}\n\n"
                f"Exported arguments are available as environment variables:\n"
                f"  cmd: ... ${name} ..."
            )

        if name not in args:
            raise ValueError(
                f"Argument '{name}' is not defined. "
                f"Required arguments must be provided."
            )

        # Convert to string (lowercase for booleans to match YAML/shell conventions)
        value = args[name]
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    return PLACEHOLDER_PATTERN.sub(replace_match, text)


def substitute_environment(text: str) -> str:
    """Substitute {{ env.NAME }} placeholders with environment variable values.

    Environment variables are read from os.environ at substitution time.

    Args:
        text: Text containing {{ env.NAME }} placeholders

    Returns:
        Text with all {{ env.NAME }} placeholders replaced

    Raises:
        ValueError: If a referenced environment variable is not set

    Example:
        >>> os.environ['USER'] = 'alice'
        >>> substitute_environment("Hello {{ env.USER }}")
        'Hello alice'
    """
    import os

    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        name = match.group(2)

        # Only substitute env: placeholders
        if prefix != "env":
            return match.group(0)  # Return unchanged

        value = os.environ.get(name)
        if value is None:
            raise ValueError(
                f"Environment variable '{name}' is not set"
            )

        return value

    return PLACEHOLDER_PATTERN.sub(replace_match, text)


def substitute_builtin_variables(text: str, builtin_vars: dict[str, str]) -> str:
    """Substitute {{ tt.name }} placeholders with built-in variable values.

    Built-in variables are system-provided values that tasks can reference.

    Args:
        text: Text containing {{ tt.name }} placeholders
        builtin_vars: Dictionary mapping built-in variable names to their string values

    Returns:
        Text with all {{ tt.name }} placeholders replaced

    Raises:
        ValueError: If a referenced built-in variable is not defined

    Example:
        >>> builtin_vars = {'project_root': '/home/user/project', 'task_name': 'build'}
        >>> substitute_builtin_variables("Root: {{ tt.project_root }}", builtin_vars)
        'Root: /home/user/project'
    """
    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        name = match.group(2)

        # Only substitute tt: placeholders
        if prefix != "tt":
            return match.group(0)  # Return unchanged

        if name not in builtin_vars:
            raise ValueError(
                f"Built-in variable '{{ tt.{name} }}' is not defined. "
                f"Available built-in variables: {', '.join(sorted(builtin_vars.keys()))}"
            )

        return builtin_vars[name]

    return PLACEHOLDER_PATTERN.sub(replace_match, text)


def substitute_dependency_args(
    template_value: str,
    parent_task_name: str,
    parent_args: dict[str, Any],
    exported_args: set[str] | None = None
) -> str:
    """Substitute {{ arg.* }} templates in dependency argument values.

    This function substitutes parent task's arguments into dependency argument
    templates. Only {{ arg.* }} placeholders are allowed in dependency arguments.

    Args:
        template_value: String that may contain {{ arg.* }} placeholders
        parent_task_name: Name of parent task (for error messages)
        parent_args: Parent task's argument values
        exported_args: Set of parent's exported argument names

    Returns:
        String with {{ arg.* }} placeholders substituted

    Raises:
        ValueError: If template references undefined arg, uses exported arg,
                   or contains non-arg placeholders ({{ var.* }}, {{ env.* }}, {{ tt.* }})

    Example:
        >>> substitute_dependency_args("{{ arg.mode }}", "build", {"mode": "debug"})
        'debug'
    """
    # Check for disallowed placeholder types in dependency args
    # Only {{ arg.* }} is allowed, not {{ var.* }}, {{ env.* }}, or {{ tt.* }}
    for match in PLACEHOLDER_PATTERN.finditer(template_value):
        prefix = match.group(1)
        name = match.group(2)

        if prefix == "var":
            raise ValueError(
                f"Task '{parent_task_name}': dependency argument contains {{ var.{name} }}\n"
                f"Template: {template_value}\n\n"
                f"Variables ({{ var.* }}) are not allowed in dependency arguments.\n"
                f"Variables are substituted at parse time, use them directly in task definitions.\n"
                f"In dependency arguments, only {{ arg.* }} templates are supported."
            )
        elif prefix == "env":
            raise ValueError(
                f"Task '{parent_task_name}': dependency argument contains {{ env.{name} }}\n"
                f"Template: {template_value}\n\n"
                f"Environment variables ({{ env.* }}) are not allowed in dependency arguments.\n"
                f"In dependency arguments, only {{ arg.* }} templates are supported."
            )
        elif prefix == "tt":
            raise ValueError(
                f"Task '{parent_task_name}': dependency argument contains {{ tt.{name} }}\n"
                f"Template: {template_value}\n\n"
                f"Built-in variables ({{ tt.* }}) are not allowed in dependency arguments.\n"
                f"In dependency arguments, only {{ arg.* }} templates are supported."
            )

    # Substitute {{ arg.* }} using parent's arguments
    try:
        return substitute_arguments(template_value, parent_args, exported_args)
    except ValueError as e:
        # Re-raise with more context
        raise ValueError(
            f"Task '{parent_task_name}': error in dependency argument substitution\n"
            f"Template: {template_value}\n"
            f"Error: {str(e)}"
        ) from e


def substitute_all(text: str, variables: dict[str, str], args: dict[str, Any]) -> str:
    """Substitute all placeholder types: variables, arguments, environment.

    Substitution order: variables → arguments → environment.
    This allows variables to contain arg/env placeholders.

    Args:
        text: Text containing placeholders
        variables: Dictionary mapping variable names to their string values
        args: Dictionary mapping argument names to their values

    Returns:
        Text with all placeholders replaced

    Raises:
        ValueError: If any referenced variable, argument, or environment variable is not defined
    """
    text = substitute_variables(text, variables)
    text = substitute_arguments(text, args)
    text = substitute_environment(text)
    return text


def substitute_dependency_outputs(
    text: str,
    current_task_name: str,
    current_task_deps: list[str],
    resolved_tasks: dict[str, Any],
) -> str:
    """Substitute {{ dep.<task>.outputs.<name> }} placeholders with dependency output paths.

    This function resolves references to named outputs from dependency tasks.
    It validates that:
    - The referenced task exists in the resolved_tasks dict
    - The current task lists the referenced task as a dependency
    - The referenced output name exists in the dependency task

    Args:
        text: Text containing {{ dep.*.outputs.* }} placeholders
        current_task_name: Name of task being resolved (for error messages)
        current_task_deps: List of dependency task names for the current task
        resolved_tasks: Dictionary mapping task names to Task objects (already resolved)

    Returns:
        Text with all {{ dep.*.outputs.* }} placeholders replaced with output paths

    Raises:
        ValueError: If referenced task doesn't exist, isn't a dependency,
                   or doesn't have the named output

    Example:
        >>> # Assuming build task has output { bundle: "dist/app.js" }
        >>> substitute_dependency_outputs(
        ...     "Deploy {{ dep.build.outputs.bundle }}",
        ...     "deploy",
        ...     ["build"],
        ...     {"build": build_task}
        ... )
        'Deploy dist/app.js'
    """
    def replacer(match: re.Match) -> str:
        dep_task_name = match.group(1)
        output_name = match.group(2)

        # Check if dependency task exists in resolved tasks
        if dep_task_name not in resolved_tasks:
            raise ValueError(
                f"Task '{current_task_name}' references output from unknown task '{dep_task_name}'.\n"
                f"Check the task name in {{{{ dep.{dep_task_name}.outputs.{output_name} }}}}"
            )

        # Check if current task depends on referenced task
        if dep_task_name not in current_task_deps:
            raise ValueError(
                f"Task '{current_task_name}' references output from '{dep_task_name}' "
                f"but does not list it as a dependency.\n"
                f"Add '{dep_task_name}' to the deps list:\n"
                f"  deps: [{', '.join(current_task_deps + [dep_task_name])}]"
            )

        # Get the dependency task
        dep_task = resolved_tasks[dep_task_name]

        # Look up the named output
        if output_name not in dep_task._output_map:
            available = list(dep_task._output_map.keys())
            available_msg = ", ".join(available) if available else "(none - all outputs are anonymous)"
            raise ValueError(
                f"Task '{current_task_name}' references output '{output_name}' "
                f"from task '{dep_task_name}', but '{dep_task_name}' has no output named '{output_name}'.\n"
                f"Available named outputs in '{dep_task_name}': {available_msg}\n"
                f"Hint: Define named outputs like: outputs: [{{ {output_name}: 'path/to/file' }}]"
            )

        return dep_task._output_map[output_name]

    return DEP_OUTPUT_PATTERN.sub(replacer, text)


def substitute_self_references(
    text: str,
    task_name: str,
    input_map: dict[str, str],
    output_map: dict[str, str],
) -> str:
    """Substitute {{ self.inputs.name }} and {{ self.outputs.name }} placeholders.

    This function resolves references to the task's own named inputs and outputs.
    Only named entries are accessible; anonymous inputs/outputs cannot be referenced.
    The substitution is literal string replacement - no glob expansion or path resolution.

    Args:
        text: Text containing {{ self.* }} placeholders
        task_name: Name of current task (for error messages)
        input_map: Dictionary mapping input names to path strings
        output_map: Dictionary mapping output names to path strings

    Returns:
        Text with all {{ self.* }} placeholders replaced with literal path strings

    Raises:
        ValueError: If referenced name doesn't exist in input_map or output_map

    Example:
        >>> input_map = {"src": "*.txt"}
        >>> output_map = {"dest": "out/result.txt"}
        >>> substitute_self_references(
        ...     "cp {{ self.inputs.src }} {{ self.outputs.dest }}",
        ...     "copy",
        ...     input_map,
        ...     output_map
        ... )
        'cp *.txt out/result.txt'
    """
    def replacer(match: re.Match) -> str:
        field = match.group(1)  # "inputs" or "outputs"
        name = match.group(2)

        # Select appropriate map
        if field == "inputs":
            name_map = input_map
            field_display = "input"
        else:  # field == "outputs"
            name_map = output_map
            field_display = "output"

        # Check if name exists in map
        if name not in name_map:
            available = list(name_map.keys())
            if available:
                available_msg = ", ".join(available)
            else:
                available_msg = f"(none - all {field} are anonymous)"

            raise ValueError(
                f"Task '{task_name}' references {field_display} '{name}' "
                f"but has no {field_display} named '{name}'.\n"
                f"Available named {field}: {available_msg}\n"
                f"Hint: Define named {field} like: {field}: [{{ {name}: 'path/to/file' }}]"
            )

        return name_map[name]

    return SELF_REFERENCE_PATTERN.sub(replacer, text)
