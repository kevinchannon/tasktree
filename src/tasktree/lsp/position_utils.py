"""Utilities for working with LSP positions in YAML documents."""

import re
import yaml
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

    This function uses YAML parsing to extract valid task names, then searches
    backwards to find which task contains the position. This approach handles
    Unicode task names and all valid YAML formats (including exotic formats
    with braces, variable indentation, etc.).

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

    # Parse YAML to get valid task names (handles Unicode, exotic formats, etc.)
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return None
        tasks = data.get("tasks", {})
        if not isinstance(tasks, dict):
            return None
        task_names = list(tasks.keys())
    except (yaml.YAMLError, AttributeError):
        return None

    if not task_names:
        return None

    # Now search for which task contains the cursor position
    # We build the text up to the cursor position and find the last task definition
    # This handles single-line YAML, multi-line YAML, any indentation, etc.

    # Build text up to cursor position
    if position.line == 0:
        text_up_to_cursor = lines[0][:position.character]
    else:
        text_up_to_cursor = '\n'.join(lines[:position.line]) + '\n' + lines[position.line][:position.character]

    # Search for all task name occurrences in the text up to cursor
    # We want the LAST (rightmost) occurrence, as that's the task we're currently in
    last_task_found = None
    last_task_pos = -1

    for task_name in task_names:
        # Create a pattern that matches the task name as a key
        # Pattern: task name followed by optional whitespace and colon
        pattern = re.escape(task_name) + r'\s*:'

        # Find all matches and get the last one
        for match in re.finditer(pattern, text_up_to_cursor):
            if match.start() > last_task_pos:
                last_task_pos = match.start()
                last_task_found = task_name

    return last_task_found


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
