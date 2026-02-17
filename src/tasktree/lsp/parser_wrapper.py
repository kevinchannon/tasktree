"""Parser wrapper for LSP to extract identifiers from tasktree YAML files."""

import re
import yaml


def extract_variables(text: str) -> list[str]:
    """Extract variable names from tasktree YAML text.

    Args:
        text: The YAML document text

    Returns:
        Alphabetically sorted list of variable names defined in the document
    """
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return []

        variables = data.get("variables", {})
        if not isinstance(variables, dict):
            return []

        return sorted(variables.keys())
    except (yaml.YAMLError, AttributeError):
        # If YAML parsing fails, return empty list (graceful degradation)
        return []


def _extract_task_args_heuristic(text: str, task_name: str) -> list[str]:
    """Extract task arguments using heuristic regex when YAML parsing fails.

    This function is used as a fallback when yaml.safe_load() fails due to
    incomplete or malformed YAML (common during LSP editing).

    Args:
        text: The YAML document text (potentially incomplete)
        task_name: The name of the task to extract arguments from

    Returns:
        List of argument names found for the task
    """
    arg_names = []

    # Escape the task name for regex matching
    escaped_task = re.escape(task_name)

    # Strategy: Find the task definition and look for args field
    # Pattern 1: Standard YAML format
    # Look for:
    #   task-name:
    #     args: [arg1, arg2] or args:\n      - arg1\n      - arg2

    # Find the task definition line
    lines = text.split('\n')
    task_line_idx = None

    for i, line in enumerate(lines):
        # Match task name as a key (with colon)
        if re.search(escaped_task + r'\s*:', line):
            task_line_idx = i
            break

    if task_line_idx is None:
        return []

    # Now search forward for args field
    # Pattern 1: Flow-style list - args: [arg1, arg2]
    flow_pattern = r'args\s*:\s*\[([^\]]*)'
    # Pattern 2: Block-style list - args:\n  - arg1

    # Search from task line onwards (but stop at next task or end of indent)
    for i in range(task_line_idx, min(task_line_idx + 20, len(lines))):
        line = lines[i]

        # Check for flow-style args
        flow_match = re.search(flow_pattern, line)
        if flow_match:
            # Extract arguments from the list
            args_content = flow_match.group(1)
            # Split by comma and extract argument names
            for arg in args_content.split(','):
                arg = arg.strip()
                if arg:
                    # Handle both simple names and dict format
                    # Simple: just "arg_name"
                    # Dict: {arg_name: ...} - we want just the name before :
                    if ':' in arg:
                        arg_name = arg.split(':')[0].strip('{} ')
                    else:
                        arg_name = arg.strip('{} "\'')
                    if arg_name:
                        arg_names.append(arg_name)
            break

        # Check for block-style args start
        if re.match(r'\s+args\s*:\s*$', line):
            # Next lines should be list items
            for j in range(i + 1, min(i + 10, len(lines))):
                item_line = lines[j]
                # Match list item: "  - arg_name" or "  - {arg_name: ...}"
                item_match = re.match(r'\s+-\s+(\S+)', item_line)
                if item_match:
                    arg = item_match.group(1)
                    # Handle dict format
                    if ':' in arg:
                        arg_name = arg.split(':')[0].strip('{} ')
                    else:
                        arg_name = arg.strip('{} "\'')
                    if arg_name:
                        arg_names.append(arg_name)
                elif re.match(r'\s+[a-zA-Z]', item_line):
                    # Hit another field, stop
                    break
            break

    return arg_names


def extract_task_args(text: str, task_name: str) -> list[str]:
    """Extract argument names for a specific task from tasktree YAML text.

    For complete YAML, uses yaml.safe_load() for accurate parsing.
    For incomplete YAML (common during LSP editing), falls back to heuristic
    regex-based extraction.

    Args:
        text: The YAML document text
        task_name: The name of the task to extract arguments from

    Returns:
        Alphabetically sorted list of argument names defined for the task
    """
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return []

        tasks = data.get("tasks", {})
        if not isinstance(tasks, dict):
            return []

        task = tasks.get(task_name)
        if not isinstance(task, dict):
            return []

        args = task.get("args", [])
        if not isinstance(args, list):
            return []

        # Extract argument names from the args list
        # Args can be either strings (positional) or dicts with name as key
        arg_names = []
        for arg in args:
            if isinstance(arg, str):
                arg_names.append(arg)
            elif isinstance(arg, dict):
                # Each dict should have exactly one key (the argument name)
                arg_names.extend(arg.keys())

        return sorted(arg_names)
    except (yaml.YAMLError, AttributeError):
        # YAML parsing failed (likely incomplete YAML during editing)
        # Fall back to heuristic extraction
        arg_names = _extract_task_args_heuristic(text, task_name)
        return sorted(arg_names)
