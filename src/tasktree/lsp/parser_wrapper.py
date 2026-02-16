"""Parser wrapper for LSP to extract identifiers from tasktree YAML files."""

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


def extract_task_args(text: str, task_name: str) -> list[str]:
    """Extract argument names for a specific task from tasktree YAML text.

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
        # If YAML parsing fails, return empty list (graceful degradation)
        return []
