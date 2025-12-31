"""Placeholder substitution for variables, arguments, and environment variables.

This module provides functions to substitute {{ var.name }}, {{ arg.name }},
and {{ env.NAME }} placeholders with their corresponding values.
"""

import re
from typing import Any


# Pattern matches: {{ prefix.name }} with optional whitespace
# Groups: (1) prefix (var|arg|env), (2) name (identifier)
PLACEHOLDER_PATTERN = re.compile(
    r'\{\{\s*(var|arg|env)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
)


def substitute_variables(text: str, variables: dict[str, str]) -> str:
    """Substitute {{ var.name }} placeholders with variable values.

    Args:
        text: Text containing {{ var.name }} placeholders
        variables: Dictionary mapping variable names to their string values

    Returns:
        Text with all {{ var.name }} placeholders replaced

    Raises:
        ValueError: If a referenced variable is not defined
    """
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

        # Convert to string
        return str(args[name])

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
