"""
The JSON schemas tasktree validates recipes against.

``schema/tasktree-schema.json`` describes a recipe *file*, which is what
editors validate as the user types. What tasktree validates at runtime is the
tree left after imports have been merged away, and that differs in exactly two
ways: imported definitions carry namespaced (dotted) names, and no ``imports``
key survives. ``merged_tree_schema`` derives the second schema from the first
so the two cannot drift apart.
"""

import copy
from typing import Any

# Name-keyed sections use these patterns to forbid dots in locally-defined
# names. After merging, dots are how a namespace is spelled, so each pattern
# gains dotted continuations. Every patternProperties key in the file schema
# must appear here -- see _rewrite_name_patterns.
_NAMESPACED_NAME_PATTERNS = {
    r"^[^.]+$": r"^[^.]+(\.[^.]+)*$",
    r"^(?!default$)[^.]+$": r"^(?!default$)[^.]+(\.[^.]+)*$",
}


def merged_tree_schema(file_schema: dict[str, Any]) -> dict[str, Any]:
    """
    Derive the merged-tree schema from the recipe file schema.

    Args:
    file_schema: The parsed contents of schema/tasktree-schema.json

    Returns:
    A new schema describing a merged recipe tree. The input is not modified.

    Raises:
    ValueError: If the file schema contains a name pattern the transform does
    not know how to namespace, which would silently reject valid imported
    names
    """
    schema = copy.deepcopy(file_schema)
    _rewrite_name_patterns(schema)
    _forbid_imports(schema)
    return schema


def _forbid_imports(schema: dict[str, Any]) -> None:
    """
    Drop 'imports' from the schema, in place.

    The merge consumes every import, so a surviving 'imports' key is a merge
    bug rather than a recipe error. Removing the property is enough to reject
    it: the top level is additionalProperties: false.
    """
    schema.get("properties", {}).pop("imports", None)
    schema["anyOf"] = [
        branch for branch in schema.get("anyOf", []) if branch != {"required": ["imports"]}
    ]


def _rewrite_name_patterns(node: Any) -> None:
    """
    Replace every patternProperties name pattern with its namespaced form,
    in place, anywhere in the schema tree.
    """
    if isinstance(node, dict):
        patterns = node.get("patternProperties")
        if isinstance(patterns, dict):
            node["patternProperties"] = {
                _namespaced_pattern(pattern): subschema
                for pattern, subschema in patterns.items()
            }
        for value in node.values():
            _rewrite_name_patterns(value)
    elif isinstance(node, list):
        for item in node:
            _rewrite_name_patterns(item)


def _namespaced_pattern(pattern: str) -> str:
    if pattern not in _NAMESPACED_NAME_PATTERNS:
        raise ValueError(
            f"Recipe schema uses an unrecognised name pattern {pattern!r}. "
            f"The merged-tree schema must namespace it, otherwise imported "
            f"definitions would be rejected. Add it to "
            f"_NAMESPACED_NAME_PATTERNS in recipe_schema.py."
        )
    return _NAMESPACED_NAME_PATTERNS[pattern]
