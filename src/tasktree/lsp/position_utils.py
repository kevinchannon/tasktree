"""Utilities for working with LSP positions in YAML documents."""

import re
from lsprotocol.types import Position


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
    # Allow position at end of line (cursor after last character)
    if position.character > len(line):
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


def get_task_at_position(text: str, position: Position) -> str | None:
    """Get the task name containing the given position.

    This function walks backwards from the current position to find the
    task definition that contains this position.

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        The task name if position is inside a task definition, None otherwise
    """
    lines = text.split("\n")

    # Check if position is within document bounds
    if position.line >= len(lines):
        return None

    # First, find "tasks:" to know the base indentation
    tasks_indent = None
    for line in lines:
        if re.match(r'^tasks:\s*$', line):
            tasks_indent = 0
            break

    if tasks_indent is None:
        return None

    # Now walk backwards from current line to find the task definition
    # We're looking for a line with exactly 2 spaces indentation (one level under "tasks:")
    for line_num in range(position.line, -1, -1):
        line = lines[line_num]

        # Check if this is a task definition at exactly 2 spaces indent
        # Pattern: "  task-name:" (exactly 2 spaces, then identifier, then colon)
        task_match = re.match(r'^  ([a-zA-Z0-9_-]+):\s*$', line)
        if task_match:
            task_name = task_match.group(1)
            return task_name

    return None


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
