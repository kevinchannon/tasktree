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

    # Walk backwards from current line to find the task definition
    # We're looking for a line like "  task-name:" at the task level
    for line_num in range(position.line, -1, -1):
        line = lines[line_num]

        # Check if this is a task definition
        # Pattern: "  task-name:" or "    task-name:" (under tasks:)
        # We need to detect the indentation level
        task_match = re.match(r'^(\s{2,})([a-zA-Z0-9_-]+):\s*$', line)
        if task_match:
            indent = task_match.group(1)
            task_name = task_match.group(2)

            # Check if this is a top-level task (under tasks:)
            # by looking backwards for "tasks:" at lower indent
            for check_line_num in range(line_num - 1, -1, -1):
                check_line = lines[check_line_num]

                # If we find "tasks:" with less indent, this is a task definition
                if re.match(r'^tasks:\s*$', check_line):
                    return task_name

                # If we find another section at same or lower indent, stop searching
                if re.match(r'^[a-zA-Z]', check_line):
                    break

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
