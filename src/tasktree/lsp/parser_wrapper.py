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
