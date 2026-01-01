"""Placeholder substitution for variables, arguments, and environment variables.

This module provides functions to substitute {{ var.name }}, {{ arg.name }},
and {{ env.NAME }} placeholders with their corresponding values.
"""

import re
from typing import Any


# Pattern matches: {{ prefix.name }} with optional whitespace
# Groups: (1) prefix (var|arg|env|tt|git), (2) name (identifier)
PLACEHOLDER_PATTERN = re.compile(
    r'\{\{\s*(var|arg|env|tt|git)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}'
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


def substitute_git_variables(text: str, working_dir: str, git_cache: dict[str, str] | None = None) -> str:
    """Substitute {{ git.name }} placeholders with git repository values.

    Git variables are cached per-invocation to avoid repeated subprocess calls.

    Args:
        text: Text containing {{ git.name }} placeholders
        working_dir: Directory to run git commands in
        git_cache: Cache dictionary for git values (shared across calls)

    Returns:
        Text with all {{ git.name }} placeholders replaced

    Raises:
        ValueError: If git command fails or repository not found

    Example:
        >>> cache = {}
        >>> substitute_git_variables("Version: {{ git.describe }}", "/path/to/repo", cache)
        'Version: v1.2.3-14-ga1b2c3d'
    """
    import subprocess
    from pathlib import Path

    # Initialize cache if not provided
    if git_cache is None:
        git_cache = {}

    # Map of git variable names to their git commands
    GIT_COMMANDS = {
        'commit': ['git', 'rev-parse', 'HEAD'],
        'commit_short': ['git', 'rev-parse', '--short', 'HEAD'],
        'branch': ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        'user_name': ['git', 'config', 'user.name'],
        'user_email': ['git', 'config', 'user.email'],
        'tag': ['git', 'describe', '--tags', '--abbrev=0'],
        'describe': ['git', 'describe', '--tags'],
        'is_dirty': ['git', 'diff-index', '--quiet', 'HEAD'],
    }

    def get_git_value(name: str) -> str:
        """Get a git variable value, using cache if available."""
        # Check cache first
        if name in git_cache:
            return git_cache[name]

        # Get the git command for this variable
        if name not in GIT_COMMANDS:
            raise ValueError(
                f"Git variable '{{ git.{name} }}' is not defined. "
                f"Available git variables: {', '.join(sorted(GIT_COMMANDS.keys()))}"
            )

        cmd = GIT_COMMANDS[name]

        # Special handling for is_dirty (uses exit code)
        if name == 'is_dirty':
            try:
                result = subprocess.run(
                    cmd,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                )
                # Exit code 0 = clean, non-zero = dirty
                value = 'false' if result.returncode == 0 else 'true'
            except Exception as e:
                raise ValueError(
                    f"Failed to get git.{name}: {e}"
                )
        else:
            # Regular command - capture stdout
            try:
                result = subprocess.run(
                    cmd,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                value = result.stdout.strip()
            except subprocess.CalledProcessError as e:
                # Provide helpful error message
                error_msg = e.stderr.strip() if e.stderr else f"exit code {e.returncode}"
                raise ValueError(
                    f"Failed to get git.{name}: {error_msg}"
                )
            except Exception as e:
                raise ValueError(
                    f"Failed to get git.{name}: {e}"
                )

        # Cache the value
        git_cache[name] = value
        return value

    def replace_match(match: re.Match) -> str:
        prefix = match.group(1)
        name = match.group(2)

        # Only substitute git: placeholders
        if prefix != "git":
            return match.group(0)  # Return unchanged

        return get_git_value(name)

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
