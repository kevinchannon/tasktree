"""Parser wrapper for LSP to extract identifiers from tasktree YAML files."""

import logging
import os
import re
import yaml

logger = logging.getLogger(__name__)


def parse_yaml_data(text: str) -> dict | None:
    """Parse YAML text and return the document data dict, or None if parsing fails.

    This is the single entry point for YAML parsing in the LSP. Callers that
    need multiple extractions from the same document should call this once and
    pass the result to each extraction function to avoid redundant parsing.

    Args:
        text: The YAML document text (may be incomplete during editing)

    Returns:
        Parsed data dict if successful, None if YAML is invalid or not a dict.
    """
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
        return None
    except (yaml.YAMLError, AttributeError) as e:
        logger.debug(f"YAML parse failed: {e}")
        return None


def extract_variables(text: str, data: dict | None = None) -> list[str]:
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
        data: Optional pre-parsed YAML data dict. If provided, skips parsing text.
              Pass the result of parse_yaml_data(text) to avoid redundant parsing.

    Returns:
        Alphabetically sorted list of variable names defined in the document.
        Returns empty list if no variables section or YAML is unparseable.
    """
    if data is None:
        data = parse_yaml_data(text)
    if data is None:
        return []

    variables = data.get("variables", {})
    if not isinstance(variables, dict):
        return []

    return sorted(variables.keys())


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


def extract_task_args(text: str, task_name: str, data: dict | None = None) -> list[str]:
    """Extract argument names for a specific task from tasktree YAML text.

    For complete YAML, uses parse_yaml_data() for accurate parsing.
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
        data: Optional pre-parsed YAML data dict. If provided, skips parsing text.
              Pass the result of parse_yaml_data(text) to avoid redundant parsing.
              Falls back to heuristic extraction if data is None and parsing fails.

    Returns:
        Alphabetically sorted list of argument names defined for the task.
        Returns empty list if task not found, has no args, or YAML is unparseable.
    """
    if data is None:
        data = parse_yaml_data(text)

    if data is not None:
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

    # YAML parsing failed (likely incomplete YAML during editing)
    # Fall back to heuristic extraction
    arg_names = _extract_task_args_heuristic(text, task_name)
    return sorted(arg_names)


def _extract_task_inputs_heuristic(text: str, task_name: str) -> list[str]:
    """Extract named inputs from potentially incomplete YAML using heuristics.

    This function is used as a fallback when yaml.safe_load() fails due to
    incomplete or malformed YAML (common during LSP editing). It uses regex
    patterns to identify named input identifiers from the text structure.

    Only extracts NAMED inputs (e.g., "source: path/to/file" or "{ source: ... }"),
    not anonymous inputs (e.g., "- path/to/file"). Anonymous inputs cannot be
    referenced via {{ self.inputs.* }} syntax.

    Handles both formats:
    - Dict format: inputs: [{ source: "path" }, { header: "path" }]
    - Key-value format: inputs:\n  - source: path\n  - header: path

    Limitations:
    - Searches up to 20 lines after task definition (performance trade-off)
    - May not handle complex nested structures correctly
    - Best-effort extraction that prioritizes availability over accuracy
    - Should only be used when yaml.safe_load() fails

    Args:
        text: The YAML document text (potentially incomplete)
        task_name: The name of the task to extract inputs from (exact match required)

    Returns:
        List of named input identifiers found for the task (may contain duplicates).
        Returns empty list if task not found or no inputs field found.
    """
    input_names = []

    # Escape the task name for regex matching
    escaped_task = re.escape(task_name)

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

    # Now search forward for inputs field
    # Pattern 1: Flow-style list - inputs: [{ source: ... }, ...]
    flow_pattern = r'inputs\s*:\s*\[([^\]]*)'

    # Search from task line onwards
    for i in range(task_line_idx, min(task_line_idx + 20, len(lines))):
        line = lines[i]

        # Check for flow-style inputs
        flow_match = re.search(flow_pattern, line)
        if flow_match:
            # Extract inputs from the list
            inputs_content = flow_match.group(1)
            # Look for dict entries: { name: ... }
            # Match opening brace, followed by identifier and colon
            dict_pattern = r'\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:'
            for match in re.finditer(dict_pattern, inputs_content):
                input_names.append(match.group(1))
            break

        # Check for block-style inputs start
        if re.match(r'\s+inputs\s*:\s*$', line):
            # Next lines should be list items
            for j in range(i + 1, min(i + 15, len(lines))):
                item_line = lines[j]
                # Match list item with dict: "  - { name: ... }" or "  - name: ..."
                # First try dict format
                dict_item_match = re.match(r'\s+-\s*\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', item_line)
                if dict_item_match:
                    input_names.append(dict_item_match.group(1))
                    continue

                # Try key-value format: "  - name: value"
                kv_item_match = re.match(r'\s+-\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:', item_line)
                if kv_item_match:
                    input_names.append(kv_item_match.group(1))
                    continue

                # Check if we hit another field (stop parsing inputs)
                if re.match(r'\s+[a-zA-Z]', item_line) and not re.match(r'\s+-', item_line):
                    break
            break

    return input_names


def extract_task_inputs(text: str, task_name: str, data: dict | None = None) -> list[str]:
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
        data: Optional pre-parsed YAML data dict. If provided, skips parsing text.
              Pass the result of parse_yaml_data(text) to avoid redundant parsing.
              Falls back to heuristic extraction if data is None and parsing fails.

    Returns:
        Alphabetically sorted list of named input identifiers defined for the task.
        Returns empty list if task not found, has no inputs, or YAML is unparseable.
    """
    if data is None:
        data = parse_yaml_data(text)

    if data is not None:
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

    # YAML parsing failed (likely incomplete YAML during editing)
    # Fall back to heuristic regex-based extraction
    input_names = _extract_task_inputs_heuristic(text, task_name)
    return sorted(input_names)


def _extract_task_outputs_heuristic(text: str, task_name: str) -> list[str]:
    """Extract named outputs from potentially incomplete YAML using heuristics.

    This function is used as a fallback when yaml.safe_load() fails due to
    incomplete or malformed YAML (common during LSP editing). It uses regex
    patterns to identify named output identifiers from the text structure.

    Only extracts NAMED outputs (e.g., "binary: path/to/file" or "{ binary: ... }"),
    not anonymous outputs (e.g., "- path/to/file"). Anonymous outputs cannot be
    referenced via {{ self.outputs.* }} syntax.

    Handles both formats:
    - Dict format: outputs: [{ binary: "path" }, { log: "path" }]
    - Key-value format: outputs:\n  - binary: path\n  - log: path

    Limitations:
    - Searches up to 20 lines after task definition (performance trade-off)
    - May not handle complex nested structures correctly
    - Best-effort extraction that prioritizes availability over accuracy
    - Should only be used when yaml.safe_load() fails

    Args:
        text: The YAML document text (potentially incomplete)
        task_name: The name of the task to extract outputs from (exact match required)

    Returns:
        List of named output identifiers found for the task (may contain duplicates).
        Returns empty list if task not found or no outputs field found.
    """
    output_names = []

    # Escape the task name for regex matching
    escaped_task = re.escape(task_name)

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

    # Now search forward for outputs field
    # Pattern 1: Flow-style list - outputs: [{ binary: ... }, ...]
    flow_pattern = r'outputs\s*:\s*\[([^\]]*)'

    # Search from task line onwards
    for i in range(task_line_idx, min(task_line_idx + 20, len(lines))):
        line = lines[i]

        # Check for flow-style outputs
        flow_match = re.search(flow_pattern, line)
        if flow_match:
            # Extract outputs from the list
            outputs_content = flow_match.group(1)
            # Look for dict entries: { name: ... }
            # Match opening brace, followed by identifier and colon
            dict_pattern = r'\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:'
            for match in re.finditer(dict_pattern, outputs_content):
                output_names.append(match.group(1))
            break

        # Check for block-style outputs start
        if re.match(r'\s+outputs\s*:\s*$', line):
            # Next lines should be list items
            for j in range(i + 1, min(i + 15, len(lines))):
                item_line = lines[j]
                # Match list item with dict: "  - { name: ... }" or "  - name: ..."
                # First try dict format
                dict_item_match = re.match(r'\s+-\s*\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', item_line)
                if dict_item_match:
                    output_names.append(dict_item_match.group(1))
                    continue

                # Try key-value format: "  - name: value"
                kv_item_match = re.match(r'\s+-\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:', item_line)
                if kv_item_match:
                    output_names.append(kv_item_match.group(1))
                    continue

                # Check if we hit another field (stop parsing outputs)
                if re.match(r'\s+[a-zA-Z]', item_line) and not re.match(r'\s+-', item_line):
                    break
            break

    return output_names


def extract_task_outputs(text: str, task_name: str, data: dict | None = None) -> list[str]:
    """Extract named output identifiers for a specific task from tasktree YAML text.

    Only extracts NAMED outputs (e.g., "binary: path/to/file"), not anonymous
    outputs (e.g., "- path/to/file"). This is because only named outputs can be
    referenced via {{ self.outputs.name }} syntax.

    Named outputs can be specified in two formats:
    1. Dict format: { name: "path/to/file" }
    2. Key-value format: name: path/to/file

    Edge cases:
    - Imported/namespaced tasks: Requires the full namespaced name (e.g., "build.compile")
    - Private tasks: Returns outputs regardless of private: true setting
    - Anonymous outputs: Ignored (returns empty list if task has only anonymous outputs)
    - Missing outputs: Returns empty list if task has no outputs defined
    - Invalid task name: Returns empty list if task doesn't exist

    Args:
        text: The YAML document text (may be incomplete during editing)
        task_name: The name of the task to extract outputs from
        data: Optional pre-parsed YAML data dict. If provided, skips parsing text.
              Pass the result of parse_yaml_data(text) to avoid redundant parsing.
              Falls back to heuristic extraction if data is None and parsing fails.

    Returns:
        Alphabetically sorted list of named output identifiers defined for the task.
        Returns empty list if task not found, has no outputs, or YAML is unparseable.
    """
    if data is None:
        data = parse_yaml_data(text)

    if data is not None:
        tasks = data.get("tasks", {})
        if not isinstance(tasks, dict):
            return []

        task = tasks.get(task_name)
        if not isinstance(task, dict):
            return []

        outputs = task.get("outputs", [])
        if not isinstance(outputs, list):
            return []

        # Extract named output identifiers from the outputs list
        # Named outputs are dicts with the output name as key
        # Anonymous outputs are strings (we skip these)
        output_names = []
        for output_item in outputs:
            if isinstance(output_item, dict):
                # Each dict should have the output name as key
                output_names.extend(output_item.keys())

        return sorted(output_names)

    # YAML parsing failed (likely incomplete YAML during editing)
    # Fall back to heuristic regex-based extraction
    output_names = _extract_task_outputs_heuristic(text, task_name)
    return sorted(output_names)


def get_env_var_names() -> list[str]:
    """Get sorted list of environment variable names from the current process environment.

    Returns all environment variable names available to the current process,
    sorted alphabetically. This is used for {{ env.* }} completion suggestions.

    The list may be long (100+ entries on typical systems), so completions are
    filtered by prefix in the completion handler.

    Returns:
        Alphabetically sorted list of environment variable names.
    """
    return sorted(os.environ.keys())
