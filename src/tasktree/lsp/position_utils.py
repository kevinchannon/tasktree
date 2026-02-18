"""Utilities for working with LSP positions in YAML documents."""

import re
import yaml
from lsprotocol.types import Position


def _is_position_valid(text: str, position: Position) -> tuple[list[str], str] | None:
    """Check if position is within document bounds and return lines and current line.

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        Tuple of (lines, current_line) if position is valid, None otherwise
    """
    lines = text.split("\n")

    # Check if position is within document bounds
    if position.line >= len(lines):
        return None

    line = lines[position.line]
    # Allow position at end of line (cursor after last character)
    if position.character > len(line):
        return None

    return (lines, line)


def is_in_cmd_field(text: str, position: Position) -> bool:
    """Check if the given position is inside a cmd field value.

    Handles both single-line and multi-line formats:
    - cmd: echo hello
    - cmd: |
        echo line 1
        echo line 2

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        True if the position is inside a cmd field value, False otherwise
    """
    result = _is_position_valid(text, position)
    if result is None:
        return False

    lines, line = result

    # Check if we're on a line that contains "cmd:" followed by text (single-line format)
    cmd_match = re.match(r'^(\s*)cmd:\s*(.*)$', line)
    if cmd_match:
        # Find where the value starts (after "cmd:")
        indent = cmd_match.group(1)
        prefix = f"{indent}cmd:"
        value_start = len(prefix)

        # Position is in cmd field if it's after "cmd:" on this line
        return position.character >= value_start

    # Check if we're in a multi-line cmd block (cmd: | or cmd: >)
    # Walk backwards to find if we're inside a cmd section
    for i in range(position.line, -1, -1):
        prev_line = lines[i]

        # Check if we hit the cmd: line with block scalar indicator
        if re.match(r'^(\s*)cmd:\s*[|>][-+]?\s*$', prev_line):
            # We're inside the cmd section
            # Position is valid anywhere on continuation lines
            return True

        # If we hit another field, we're not in cmd
        if re.match(r'^(\s*)[a-zA-Z_][a-zA-Z0-9_]*:\s*', prev_line):
            return False

    return False


def is_in_working_dir_field(text: str, position: Position) -> bool:
    """Check if the given position is inside a working_dir field value.

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        True if the position is inside a working_dir field value, False otherwise
    """
    result = _is_position_valid(text, position)
    if result is None:
        return False

    lines, line = result

    # Check if we're on a line that contains "working_dir:" followed by text
    working_dir_match = re.match(r'^(\s*)working_dir:\s*(.*)$', line)
    if working_dir_match:
        # Find where the value starts (after "working_dir:")
        indent = working_dir_match.group(1)
        prefix = f"{indent}working_dir:"
        value_start = len(prefix)

        # Position is in working_dir field if it's after "working_dir:" on this line
        return position.character >= value_start

    return False


def _is_in_list_field(text: str, position: Position, field_name: str) -> bool:
    """Check if the given position is inside a list field value (generic helper).

    Handles both single-line and list formats:
    - field_name: ["value"]
    - field_name:
        - "value"

    Args:
        text: The full document text
        position: The position to check (line and character)
        field_name: The name of the field to check (e.g., "outputs", "deps", "inputs")

    Returns:
        True if the position is inside the field value, False otherwise
    """
    result = _is_position_valid(text, position)
    if result is None:
        return False

    lines, line = result

    # Check if we're on a line that contains "field_name:" followed by text (single-line format)
    field_match = re.match(rf'^(\s*){re.escape(field_name)}:\s*(.*)$', line)
    if field_match:
        # Find where the value starts (after "field_name:")
        indent = field_match.group(1)
        prefix = f"{indent}{field_name}:"
        value_start = len(prefix)

        # Position is in field if it's after "field_name:" on this line
        return position.character >= value_start

    # Check if we're in a list item under field_name (multi-line format)
    # Walk backwards to find if we're inside the field section
    for i in range(position.line, -1, -1):
        prev_line = lines[i]

        # Check if we hit the field_name: line
        if re.match(rf'^(\s*){re.escape(field_name)}:\s*$', prev_line):
            # We're inside the field section - check if current line is a list item
            list_item_match = re.match(r'^(\s*)-\s+', line)
            if list_item_match:
                # Position must be after the "- " part
                return position.character >= len(list_item_match.group(0))
            return False

        # If we hit another field at the same or lower indentation, we're not in this field
        if re.match(r'^(\s*)[a-zA-Z_][a-zA-Z0-9_]*:\s*', prev_line):
            return False

    return False


def is_in_outputs_field(text: str, position: Position) -> bool:
    """Check if the given position is inside an outputs field value.

    Handles both single-line and list formats:
    - outputs: ["file-{{ arg.name }}.txt"]
    - outputs:
        - "file-{{ arg.name }}.txt"

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        True if the position is inside an outputs field value, False otherwise
    """
    return _is_in_list_field(text, position, "outputs")


def is_in_deps_field(text: str, position: Position) -> bool:
    """Check if the given position is inside a deps field value.

    Handles both single-line and list formats:
    - deps: [task({{ arg.value }})]
    - deps:
        - task: [{{ arg.value }}]

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        True if the position is inside a deps field value, False otherwise
    """
    return _is_in_list_field(text, position, "deps")


def is_in_substitutable_field(text: str, position: Position) -> bool:
    """Check if position is in a field that supports arg.* and self.* substitutions.

    These substitutions are valid in:
    - cmd field
    - working_dir field
    - outputs field (for output paths with arg templates)
    - deps field (for parameterized dependency arguments)
    - args[].default field (argument defaults)

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        True if the position is in a field supporting substitutions, False otherwise
    """
    # Check cmd, working_dir, outputs, and deps fields
    if (is_in_cmd_field(text, position) or
        is_in_working_dir_field(text, position) or
        is_in_outputs_field(text, position) or
        is_in_deps_field(text, position)):
        return True

    # Check if we're in an args default field
    # This is a bit more complex as defaults can be nested inside args
    lines = text.split("\n")
    if position.line >= len(lines):
        return False

    line = lines[position.line]
    if position.character > len(line):
        return False

    # Check for block-style "default:" field pattern
    default_match = re.match(r'^(\s*)default:\s*(.*)$', line)
    if default_match:
        indent = default_match.group(1)
        prefix = f"{indent}default:"
        value_start = len(prefix)
        return position.character >= value_start

    # Check for flow-style default: { default: "value" }
    # Look for pattern: default: followed by quote or opening brace
    flow_default_match = re.search(r'default:\s*["{]', line)
    if flow_default_match:
        # Position is in default if it's after "default:"
        default_start = flow_default_match.start() + len("default:")
        return position.character >= default_start

    return False


def _extract_task_names_heuristic(text: str) -> list[str]:
    """Extract task names from potentially incomplete YAML using heuristics.

    This function is used as a fallback when yaml.safe_load() fails due to
    incomplete or malformed YAML (common during LSP editing). It uses regex
    patterns to identify task names from the text structure.

    Handles both standard YAML format:
        tasks:
          task-name:
            cmd: ...

    And flow-style format:
        tasks: {task-name: {cmd: ...}, ...}

    Filters out known field names (cmd, args, deps, etc.) to avoid false positives.
    Supports Unicode task names (emojis, non-ASCII characters).

    Limitations:
    - May not handle deeply nested or complex YAML structures correctly
    - Best-effort extraction that prioritizes availability over accuracy
    - Should only be used when yaml.safe_load() fails

    Args:
        text: The YAML document text (potentially incomplete)

    Returns:
        List of task names found in the text (may contain duplicates).
        Returns empty list if no tasks pattern is found.
    """
    task_names = []

    # Pattern 1: Standard YAML - "tasks:" followed by indented task definitions
    # Match: tasks:\n  task-name:
    # We look for lines after "tasks:" that have any indentation followed by any non-whitespace
    # characters (the task name) and a colon
    lines = text.split("\n")
    in_tasks_section = False

    for i, line in enumerate(lines):
        # Check if we're entering the tasks section
        if re.match(r'^\s*tasks\s*:\s*$', line):
            in_tasks_section = True
            continue

        # Check if we're leaving the tasks section (new top-level key)
        if in_tasks_section and re.match(r'^[a-zA-Z]', line):
            in_tasks_section = False
            continue

        # Extract task names from indented lines in tasks section
        if in_tasks_section:
            # Match any indented line with pattern: whitespace + task-name + colon
            # Task name can be any non-whitespace characters (including Unicode)
            match = re.match(r'^\s+(\S+?)\s*:\s*', line)
            if match:
                task_name = match.group(1)
                # Filter out field names that are not task names
                if task_name not in ['cmd', 'args', 'deps', 'desc', 'inputs', 'outputs',
                                     'working_dir', 'run_in', 'private', 'pin_runner']:
                    task_names.append(task_name)

    # Pattern 2: Flow-style YAML - tasks: {task1: {...}, task2: {...}}
    # Look for "tasks:" followed by opening brace, then extract keys
    flow_pattern = r'tasks\s*:\s*\{([^}]*)'
    flow_match = re.search(flow_pattern, text, re.DOTALL)
    if flow_match:
        # Extract the content inside the braces
        content = flow_match.group(1)
        # Find all task names - pattern: any characters followed by colon
        # We need to be careful with nested braces
        task_pattern = r'(\S+?)\s*:\s*\{'
        for match in re.finditer(task_pattern, content):
            task_name = match.group(1)
            if task_name not in task_names:
                task_names.append(task_name)

    return task_names


def _find_task_containing_position(task_names: list[str], lines: list[str], position: Position) -> str | None:
    """Find which task definition contains the given position.

    Searches through the document to find the most recent task definition
    that appears at or before the cursor position. This handles cases where
    multiple tasks are defined in the document.

    The function searches for each task name followed by a colon (using exact
    string matching with regex escaping) and returns the task whose definition
    line is closest to but not after the cursor position.

    Args:
        task_names: List of valid task names to search for (can include Unicode)
        lines: Document text split into lines
        position: The position to check (line and character)

    Returns:
        The task name if a task definition is found at or before position, None otherwise.
        Returns the rightmost (in same line) or bottommost (in earlier line) task
        definition when multiple tasks appear before the cursor.
    """
    # For each task name, find all occurrences and check if they're before cursor
    last_task_found = None
    last_task_line = -1
    last_task_char = -1

    for task_name in task_names:
        # Create a pattern that matches the task name as a key
        # Pattern: task name followed by optional whitespace and colon
        pattern = re.escape(task_name) + r'\s*:'

        # Search through each line
        for line_num, line in enumerate(lines):
            for match in re.finditer(pattern, line):
                # Check if this match is before or at the cursor position
                if line_num < position.line or (line_num == position.line and match.start() <= position.character):
                    # This match is valid - check if it's the most recent one
                    if line_num > last_task_line or (line_num == last_task_line and match.start() > last_task_char):
                        last_task_found = task_name
                        last_task_line = line_num
                        last_task_char = match.start()

    return last_task_found


def get_task_at_position(text: str, position: Position) -> str | None:
    """Get the task name containing the given position.

    This function uses YAML parsing to extract valid task names, then searches
    backwards to find which task contains the position. This approach handles
    Unicode task names and all valid YAML formats (including exotic formats
    with braces, variable indentation, etc.).

    For incomplete YAML (common during LSP editing), falls back to regex-based
    heuristic parsing to extract task names from the text structure.

    Edge cases:
    - Imported/namespaced tasks: Returns the namespaced name (e.g., "build.compile")
    - Private tasks: Returns the task name regardless of private: true setting
    - Multiline cmd fields: Correctly identifies the task for all lines in the cmd block
    - Nested blocks: Returns the most recent task definition before the cursor

    Args:
        text: The full document text
        position: The position to check (line and character)

    Returns:
        The task name if position is inside a task definition, None otherwise.
        Returns None if position is before any task definition or outside the
        tasks section entirely.
    """
    lines = text.split("\n")

    # Check if position is within document bounds
    if position.line >= len(lines):
        return None

    # Parse YAML to get valid task names (handles Unicode, exotic formats, etc.)
    task_names = []
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            tasks = data.get("tasks", {})
            if isinstance(tasks, dict):
                task_names = list(tasks.keys())
    except (yaml.YAMLError, AttributeError):
        # YAML parsing failed (likely incomplete YAML during editing)
        # Fall back to heuristic regex-based extraction
        task_names = _extract_task_names_heuristic(text)

    if not task_names:
        return None

    # Find which task contains the cursor position
    return _find_task_containing_position(task_names, lines, position)


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
