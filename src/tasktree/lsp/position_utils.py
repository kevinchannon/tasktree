"""Utilities for working with LSP positions in YAML documents.

Position detection is now delegated to ts_context.py which uses
tree-sitter for error-tolerant structural detection, replacing the
previous regex/indentation heuristic approach.

Two pure-string helpers (get_prefix_at_position, is_inside_open_template)
are unchanged as they do not depend on YAML structure.
"""

from lsprotocol.types import Position
from tree_sitter import Tree

from tasktree.lsp.ts_context import (
    get_task_at_position as _ts_get_task_at_position,
    is_in_field as _ts_is_in_field,
    is_in_substitutable_field as _ts_is_in_substitutable_field,
)


# ---------------------------------------------------------------------------
# Field detection — delegates to tree-sitter context
# ---------------------------------------------------------------------------


def is_in_cmd_field(tree: Tree, position: Position) -> bool:
    """Return True if *position* is inside the value of a ``cmd:`` field.

    Works for both single-line and multi-line (block scalar) formats.

    Args:
        tree:     Tree-sitter parse tree for the document.
        position: LSP cursor position (zero-based line and character).
    """
    return _ts_is_in_field(tree, position.line, position.character, "cmd")


def is_in_working_dir_field(tree: Tree, position: Position) -> bool:
    """Return True if *position* is inside the value of a ``working_dir:`` field.

    Args:
        tree:     Tree-sitter parse tree for the document.
        position: LSP cursor position.
    """
    return _ts_is_in_field(
        tree, position.line, position.character, "working_dir"
    )


def is_in_outputs_field(tree: Tree, position: Position) -> bool:
    """Return True if *position* is inside an ``outputs:`` field value.

    Handles both single-line flow style and multi-line list format.

    Args:
        tree:     Tree-sitter parse tree for the document.
        position: LSP cursor position.
    """
    return _ts_is_in_field(tree, position.line, position.character, "outputs")


def is_in_deps_field(tree: Tree, position: Position) -> bool:
    """Return True if *position* is inside a ``deps:`` field value.

    Handles both single-line flow style and multi-line list format.

    Args:
        tree:     Tree-sitter parse tree for the document.
        position: LSP cursor position.
    """
    return _ts_is_in_field(tree, position.line, position.character, "deps")


def is_in_substitutable_field(tree: Tree, position: Position) -> bool:
    """Return True if *position* is in a field supporting substitutions.

    Substitution prefixes (``{{ arg.* }}``, ``{{ self.inputs.* }}``,
    ``{{ self.outputs.* }}``) are valid in: ``cmd``, ``working_dir``,
    ``outputs``, ``deps``, and ``default`` (for args[].default).

    Args:
        tree:     Tree-sitter parse tree for the document.
        position: LSP cursor position.
    """
    return _ts_is_in_substitutable_field(
        tree, position.line, position.character
    )


def get_task_at_position(tree: Tree, position: Position) -> str | None:
    """Return the name of the task whose definition contains *position*.

    Uses the tree-sitter parse tree to walk the tasks mapping and find
    the task pair whose start is closest to (but not past) the cursor.

    Args:
        tree:     Tree-sitter parse tree for the document.
        position: LSP cursor position.

    Returns:
        Task name string, or ``None`` if no task contains the position.
    """
    return _ts_get_task_at_position(tree, position.line, position.character)


# ---------------------------------------------------------------------------
# Pure-string helpers — unchanged from original implementation
# ---------------------------------------------------------------------------


def is_inside_open_template(prefix: str) -> bool:
    """Return True if the cursor is inside an unclosed ``{{ }}`` template.

    Scans the prefix (text from line start to cursor) for the last ``{{``.
    If no ``}}`` follows it, the cursor is inside an open template.

    This distinguishes:
    - Cursor typing a task name:  ``"  - build_ta"``   (no open template)
    - Cursor inside a template:   ``"  - {{ arg."``    (inside open template)

    Args:
        prefix: Text from the start of the current line to the cursor.

    Returns:
        True if the cursor is inside an unclosed ``{{ }}`` expression.
    """
    last_open_idx = prefix.rfind("{{")
    if last_open_idx == -1:
        return False
    return "}}" not in prefix[last_open_idx:]


def get_prefix_at_position(text: str, position: Position) -> str:
    """Return the text from the start of the cursor's line to the cursor.

    Args:
        text:     Full document text.
        position: LSP cursor position.

    Returns:
        Prefix string (empty string if position is out of bounds).
    """
    lines = text.split("\n")
    if position.line >= len(lines):
        return ""
    line = lines[position.line]
    return line[: position.character]
