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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jsonschema import ValidationError

SCHEMA_FILENAME = "tasktree-schema.json"

# Name-keyed sections use these patterns to forbid dots in locally-defined
# names. In a merged tree dots are how a namespace is spelled, and names are
# not the schema's business at all: the merge reports a bad local name against
# the file that defined it, and does so lazily, so a name nothing references
# never breaks a run. The rewritten patterns therefore accept any name and
# exist only to route each value to its schema -- except that 'default' must
# keep failing to match, since there it declares the default runner or
# interpreter rather than naming one. Every patternProperties key in the file
# schema must appear here -- see _rewrite_name_patterns.
_NAMESPACED_NAME_PATTERNS = {
    r"^[^.]+$": r"^.*$",
    r"^(?!default$)[^.]+$": r"^(?!default$).*$",
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


def schema_error_message(error: "ValidationError", recipe_path: Path) -> str:
    """
    Render a schema validation failure as something a recipe author can act on.

    jsonschema's own message dumps the failing subschema, which for a recipe
    means pages of JSON. This keeps the part that identifies the problem and
    says where it is in the recipe's own terms.

    Args:
    error: The validation error, ideally from jsonschema's best_match
    recipe_path: Path of the recipe being validated, for the message

    Returns:
    A one-or-two-line message naming the file, the location and the problem
    """
    location = _recipe_location(error)
    where = f"{recipe_path}: {location}" if location else str(recipe_path)
    message = f"{where}: {_plain_reason(error)}"
    hint = _remediation_hint(error)
    return f"{message}\n{hint}" if hint else message


def _remediation_hint(error: "ValidationError") -> str:
    """
    Tasktree-specific advice for mistakes the schema can only describe.

    The schema knows `args` must be an array; it cannot know that writing it
    as a mapping is the common slip, nor show the list form. Hand-written
    checks used to carry advice like this, so it lives here as they retire.
    """
    path = list(error.absolute_path)
    if path and path[-1] == "args" and error.validator == "type":
        example = "name"
        if isinstance(error.instance, dict) and error.instance:
            example = str(next(iter(error.instance)))
        return (
            f"Arguments are a list, one entry per line:\n"
            f"  args:\n"
            f"    - {example}: {{ type: str }}"
        )
    return ""


def _recipe_location(error: "ValidationError") -> str:
    """
    Describe where the error is, the way the recipe is written: dotted for
    mapping keys, indexed for list entries, bracketed for names that already
    contain dots ('tasks[\'build.release\']').
    """
    location = ""
    for part in error.absolute_path:
        if isinstance(part, int):
            location += f"[{part}]"
        elif "." in part:
            location += f"['{part}']"
        else:
            location += f".{part}" if location else part
    return location


def _plain_reason(error: "ValidationError") -> str:
    """
    The reason a value was rejected, without schema internals.

    Two constructs need rewording; the rest of jsonschema's messages are
    already plain enough ("'cmd' is a required property").
    """
    if error.validator in {"oneOf", "anyOf"}:
        return _accepted_forms_reason(error)
    if error.validator == "not":
        return _wrong_kind_reason(error)
    return error.message


def _accepted_forms_reason(error: "ValidationError") -> str:
    """
    Reword "is not valid under any of the given schemas", which jsonschema
    follows with every branch's full JSON.

    The branch descriptions are the useful part -- and the *enclosing*
    schema's description must not be used instead, since for a name-keyed
    section it describes the key rather than the value.
    """
    branches = error.schema.get(error.validator, []) if isinstance(error.schema, dict) else []
    forms = [
        branch["description"]
        for branch in branches
        if isinstance(branch, dict) and branch.get("description")
    ]
    if forms:
        return f"{error.instance!r} is not valid here. Expected one of: {'; '.join(forms)}"
    return f"{error.instance!r} is not one of the accepted forms here"


def _wrong_kind_reason(error: "ValidationError") -> str:
    """
    Reword "should not be valid under {'required': [...]}".

    The schema uses 'not: {required: [...]}' only to keep a runner kind's
    fields off the other kinds, so the failure always means the author put a
    field on a runner whose 'type' doesn't have it.
    """
    negated = error.validator_value if isinstance(error.validator_value, dict) else {}
    forbidden = negated.get("required", [])
    named = ", ".join(f"'{key}'" for key in forbidden)
    return (
        f"{named} is not valid for this runner's type. Set 'type' (and "
        f"'engine' for containerised runners) to a kind that supports it."
    )


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
