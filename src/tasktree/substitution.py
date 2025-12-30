"""Placeholder substitution for variables and arguments.

This module provides functions to substitute {{ var.name }} and {{ arg.name }}
placeholders with their corresponding values.
"""

import re
from typing import Any


# Pattern matches: {{ prefix.name }} with optional whitespace
# Groups: (1) prefix (var|arg), (2) name (identifier)
PLACEHOLDER_PATTERN = re.compile(
    r'\{\{\s*(var|arg)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
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


def substitute_arguments(text: str, args: dict[str, Any]) -> str:
    """Substitute {{ arg.name }} placeholders with argument values.

    Args:
        text: Text containing {{ arg.name }} placeholders
        args: Dictionary mapping argument names to their values

    Returns:
        Text with all {{ arg.name }} placeholders replaced

    Raises:
        ValueError: If a referenced argument is not provided
    """
    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        name = match.group(2)

        # Only substitute arg: placeholders
        if prefix != "arg":
            return match.group(0)  # Return unchanged

        if name not in args:
            raise ValueError(
                f"Argument '{name}' is not defined. "
                f"Required arguments must be provided."
            )

        # Convert to string
        return str(args[name])

    return PLACEHOLDER_PATTERN.sub(replace_match, text)


def substitute_all(text: str, variables: dict[str, str], args: dict[str, Any]) -> str:
    """Substitute both {{ var.name }} and {{ arg.name }} placeholders.

    Variables are substituted first, then arguments.

    Args:
        text: Text containing placeholders
        variables: Dictionary mapping variable names to their string values
        args: Dictionary mapping argument names to their values

    Returns:
        Text with all placeholders replaced

    Raises:
        ValueError: If any referenced variable or argument is not defined
    """
    text = substitute_variables(text, variables)
    text = substitute_arguments(text, args)
    return text
