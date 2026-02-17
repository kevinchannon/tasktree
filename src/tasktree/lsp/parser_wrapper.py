"""Parser wrapper for LSP to extract identifiers from tasktree YAML files."""

import logging
import re
import yaml

logger = logging.getLogger(__name__)


def extract_variables(text: str) -> list[str]:
    """Extract variable names from tasktree YAML text.

    Extracts variable names from the variables section, handling all variable
    definition formats (simple values, env, eval, read).

    Edge cases:
    - Complex variables: Extracts names from {env: VAR}, {eval: "cmd"}, {read: path} formats
    - Missing variables section: Returns empty list
    - Incomplete YAML: Returns empty list (graceful degradation during editing)
    - Invalid YAML: Returns empty list and logs debug message

    Args:
        text: The YAML document text (may be incomplete during editing)

    Returns:
        Alphabetically sorted list of variable names defined in the document.
        Returns empty list if no variables section or YAML is unparseable.
    """
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return []

        variables = data.get("variables", {})
        if not isinstance(variables, dict):
            return []

        return sorted(variables.keys())
    except (yaml.YAMLError, AttributeError) as e:
        # If YAML parsing fails, return empty list (graceful degradation)
        logger.debug(f"YAML parse failed for variable extraction: {e}")
        return []


def _extract_task_args_heuristic(text: str, task_name: str) -> list[str]:
    """Extract task arguments using heuristic regex when YAML parsing fails.

    This function is used as a fallback when yaml.safe_load() fails due to
    incomplete or malformed YAML (common during LSP editing).

    Handles both flow-style (args: [arg1, arg2]) and block-style formats.
    Supports both simple string args and dict-format args with type information.

    Limitations:
    - Searches up to 20 lines after task definition (performance trade-off)
    - May not handle complex nested structures correctly
    - Best-effort extraction that prioritizes availability over accuracy
    - Should only be used when yaml.safe_load() fails

    Args:
        text: The YAML document text (potentially incomplete)
        task_name: The name of the task to extract arguments from (exact match required)

    Returns:
        List of argument names found for the task (may contain duplicates).
        Returns empty list if task not found or no args field found.
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

    Edge cases:
    - Imported/namespaced tasks: Requires the full namespaced name (e.g., "build.compile")
    - Private tasks: Returns args regardless of private: true setting
    - Dict-format args: Extracts the argument name from {name: {type: str, ...}} format
    - Simple string args: Handles both ["arg1", "arg2"] and flow-style formats
    - Missing args: Returns empty list if task has no args defined
    - Invalid task name: Returns empty list if task doesn't exist

    Args:
        text: The YAML document text (may be incomplete during editing)
        task_name: The name of the task to extract arguments from

    Returns:
        Alphabetically sorted list of argument names defined for the task.
        Returns empty list if task not found, has no args, or YAML is unparseable.
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
    except (yaml.YAMLError, AttributeError) as e:
        # YAML parsing failed (likely incomplete YAML during editing)
        # Fall back to heuristic extraction
        logger.debug(f"YAML parse failed for task args extraction: {e}")
        arg_names = _extract_task_args_heuristic(text, task_name)
        return sorted(arg_names)


def extract_task_inputs(text: str, task_name: str) -> list[str]:
    """Extract named input identifiers for a specific task from tasktree YAML text.

    Only extracts NAMED inputs (e.g., "source: path/to/file"), not anonymous
    inputs (e.g., "- path/to/file"). This is because only named inputs can be
    referenced via {{ self.inputs.name }} syntax.

    Named inputs can be specified in two formats:
    1. Dict format: { name: "path/to/file" }
    2. Key-value format: name: path/to/file

    Edge cases:
    - Imported/namespaced tasks: Requires the full namespaced name (e.g., "build.compile")
    - Private tasks: Returns inputs regardless of private: true setting
    - Anonymous inputs: Ignored (returns empty list if task has only anonymous inputs)
    - Missing inputs: Returns empty list if task has no inputs defined
    - Invalid task name: Returns empty list if task doesn't exist

    Args:
        text: The YAML document text (may be incomplete during editing)
        task_name: The name of the task to extract inputs from

    Returns:
        Alphabetically sorted list of named input identifiers defined for the task.
        Returns empty list if task not found, has no inputs, or YAML is unparseable.
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

        inputs = task.get("inputs", [])
        if not isinstance(inputs, list):
            return []

        # Extract named input identifiers from the inputs list
        # Named inputs are dicts with the input name as key
        # Anonymous inputs are strings (we skip these)
        input_names = []
        for input_item in inputs:
            if isinstance(input_item, dict):
                # Each dict should have the input name as key
                input_names.extend(input_item.keys())

        return sorted(input_names)
    except (yaml.YAMLError, AttributeError) as e:
        # YAML parsing failed (likely incomplete YAML during editing)
        # Return empty list (no heuristic fallback for now)
        logger.debug(f"YAML parse failed for task inputs extraction: {e}")
        return []
