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
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_FILENAME = "tasktree-schema.json"

# Name-keyed sections use these patterns to forbid dots in locally-defined
# names. After merging, dots are how a namespace is spelled, so each pattern
# gains dotted continuations. Every patternProperties key in the file schema
# must appear here -- see _rewrite_name_patterns.
_NAMESPACED_NAME_PATTERNS = {
    r"^[^.]+$": r"^[^.]+(\.[^.]+)*$",
    r"^(?!default$)[^.]+$": r"^(?!default$)[^.]+(\.[^.]+)*$",
}


def schema_candidates() -> tuple[Path, ...]:
    """
    Where the recipe file schema may live, most-installed first.

    The schema is authored at the repository root so the raw-GitHub URL in the
    READMEs -- the one users point their editors at -- keeps working. The wheel
    build force-includes it under the package (see pyproject.toml), which is
    where an installed tasktree finds it; a source checkout falls back to the
    authored copy.
    """
    return (
        Path(__file__).parent / "schema" / SCHEMA_FILENAME,
        Path(__file__).parents[2] / "schema" / SCHEMA_FILENAME,
    )


def schema_path() -> Path:
    """
    Locate the recipe file schema.

    Raises:
    FileNotFoundError: If no copy is present, which means a broken install
    """
    for candidate in schema_candidates():
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(path) for path in schema_candidates())
    raise FileNotFoundError(
        f"Recipe schema {SCHEMA_FILENAME} not found (looked in: {searched}). "
        f"This tasktree installation is incomplete."
    )


@lru_cache(maxsize=1)
def load_file_schema() -> dict[str, Any]:
    """
    Load the recipe file schema, which describes a single recipe file as the
    user authors it. Cached: it is read on every parse and never changes
    within a run.
    """
    return json.loads(schema_path().read_text())


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
    _allow_empty_tree(schema)
    return schema


def _forbid_imports(schema: dict[str, Any]) -> None:
    """
    Drop 'imports' from the schema, in place.

    The merge consumes every import, so a surviving 'imports' key is a merge
    bug rather than a recipe error. Removing the property is enough to reject
    it: the top level is additionalProperties: false.
    """
    schema.get("properties", {}).pop("imports", None)


def _allow_empty_tree(schema: dict[str, Any]) -> None:
    """
    Drop the "at least one section" requirement, in place.

    An empty recipe is valid to tt, and the file schema's requirement is
    editor guidance for someone writing a file from scratch -- not something
    a merged tree has to satisfy.
    """
    schema.pop("anyOf", None)


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
