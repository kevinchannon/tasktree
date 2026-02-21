"""Parser wrapper for LSP identifier extraction.

All YAML parsing and structural extraction is delegated to ts_context.py
which uses tree-sitter for error-tolerant parsing.  This module provides
thin wrappers that match the external API expected by server.py.

get_env_var_names() is unchanged — it reads the process environment and
has no dependency on YAML structure.
"""

import logging
import os

from tree_sitter import Tree

from tasktree.lsp.ts_context import (
    extract_variables as _ts_extract_variables,
    extract_task_args as _ts_extract_task_args,
    extract_task_inputs as _ts_extract_task_inputs,
    extract_task_outputs as _ts_extract_task_outputs,
    extract_task_names as _ts_extract_task_names,
)

logger = logging.getLogger(__name__)


def extract_variables(tree: Tree) -> list[str]:
    """Extract variable names from the ``variables:`` section.

    Args:
        tree: Tree-sitter parse tree for the document.

    Returns:
        Alphabetically sorted list of variable names.
        Empty list if no variables section or on error.
    """
    return _ts_extract_variables(tree)


def extract_task_args(tree: Tree, task_name: str) -> list[str]:
    """Extract argument names for a specific task.

    Handles both the string format (``- arg_name``) and the dict format
    (``- arg_name: {type: str, …}``).

    Args:
        tree:      Tree-sitter parse tree for the document.
        task_name: Name of the task to inspect.

    Returns:
        Alphabetically sorted list of argument names.
        Empty list if the task is not found or has no args.
    """
    return _ts_extract_task_args(tree, task_name)


def extract_task_inputs(tree: Tree, task_name: str) -> list[str]:
    """Extract named input identifiers for a specific task.

    Only *named* inputs (dict items like ``- source: path/to/file``) are
    returned.  Anonymous inputs (plain strings) are skipped because they
    cannot be referenced via ``{{ self.inputs.name }}`` syntax.

    Args:
        tree:      Tree-sitter parse tree for the document.
        task_name: Name of the task to inspect.

    Returns:
        Alphabetically sorted list of named input identifiers.
    """
    return _ts_extract_task_inputs(tree, task_name)


def extract_task_outputs(tree: Tree, task_name: str) -> list[str]:
    """Extract named output identifiers for a specific task.

    Only *named* outputs (dict items like ``- binary: dist/app``) are
    returned.  Anonymous outputs (plain strings) are skipped because they
    cannot be referenced via ``{{ self.outputs.name }}`` syntax.

    Args:
        tree:      Tree-sitter parse tree for the document.
        task_name: Name of the task to inspect.

    Returns:
        Alphabetically sorted list of named output identifiers.
    """
    return _ts_extract_task_outputs(tree, task_name)


def extract_task_names(
    tree: Tree, base_path: str | None = None
) -> list[str]:
    """Extract task names from the document, including from imported files.

    Local task names come from the ``tasks:`` section.  If ``base_path``
    is provided, imported files are resolved relative to it and their task
    names are included with the ``namespace.`` prefix from ``imports[].as``.

    Limitation: only one level of imports is resolved.

    Args:
        tree:      Tree-sitter parse tree for the document.
        base_path: Directory of the current file for resolving imports.
                   Pass ``None`` to skip import resolution.

    Returns:
        Alphabetically sorted list of all available task names.
    """
    return _ts_extract_task_names(tree, base_path)


def get_env_var_names() -> list[str]:
    """Return a sorted list of environment variable names.

    Returns all variable names available to the current process,
    sorted alphabetically.  Used for ``{{ env.* }}`` completion.

    Returns:
        Alphabetically sorted list of environment variable names.
    """
    return sorted(os.environ.keys())
