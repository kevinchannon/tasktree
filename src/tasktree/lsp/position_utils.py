"""Utilities for working with LSP positions in YAML documents."""

import re
from pygls.lsp.types import Position


def is_in_cmd_field(text: str, position: Position) -> bool:
    """Check if the given position is inside a cmd field value.

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        True if the position is inside a cmd field value, False otherwise
    """
    lines = text.split("\n")

    # Check if position is within document bounds
    if position.line >= len(lines):
        return False

    line = lines[position.line]
    if position.character >= len(line):
        return False

    # Simple heuristic: if we're on a line that contains "cmd:" followed by text,
    # and the position is after "cmd:", we're in a cmd field
    cmd_match = re.match(r'^(\s*)cmd:\s*(.*)$', line)
    if cmd_match:
        # Find where the value starts (after "cmd:")
        indent = cmd_match.group(1)
        prefix = f"{indent}cmd:"
        value_start = len(prefix)

        # Position is in cmd field if it's after "cmd:" on this line
        return position.character >= value_start

    return False


def get_prefix_at_position(text: str, position: Position) -> str:
    """Get the text prefix up to the cursor position.

    This is useful for determining what the user is typing for completion.

    Args:
        text: The full document text
        position: The cursor position

    Returns:
        The text from the start of the line up to the cursor position
    """
    lines = text.split("\n")

    # Check if position is within document bounds
    if position.line >= len(lines):
        return ""

    line = lines[position.line]
    # Return text up to the cursor position
    return line[: position.character]
