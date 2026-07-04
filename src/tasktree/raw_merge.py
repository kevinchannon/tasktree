"""
Raw-dict import merging for the schema-validation pipeline (issue #43, slice 4).

Merges a recipe file and all of its imports into a single raw dict *before*
any Task/Runner object is constructed. Namespacing, run_in blanket overrides
and pinned-runner rewrites are applied as dict transforms, so the result is
what the runtime schema validation (slice 6) will validate. Built additively
alongside the object-building path in parser.py; sections cut over one at a
time.
"""

from pathlib import Path
from typing import Any

import yaml


class CircularImportError(Exception):
    """
    Raised when a circular import is detected.
    """

    pass


def merge_recipe(recipe_path: Path) -> dict[str, Any]:
    """
    Merge a recipe file and its imports into a single raw dict.

    The 'imports' key is consumed by the merge and never appears in the
    result (its presence downstream would indicate a merge bug).

    Args:
    recipe_path: Path to the main recipe file

    Returns:
    The merged raw recipe dict (empty dict for an empty file)

    Raises:
    FileNotFoundError: If an imported file doesn't exist
    CircularImportError: If a circular import is detected
    """
    return _merge_file(recipe_path, namespace=None, import_stack=[])


def _merge_file(
    file_path: Path,
    namespace: str | None,
    import_stack: list[Path],
) -> dict[str, Any]:
    """
    Load one file and fold its imports in, applying namespace transforms.

    Args:
    file_path: Path to the YAML file
    namespace: Full namespace chain for this file (None for the root file)
    import_stack: Files currently being imported (for circular detection)
    """
    if file_path in import_stack:
        chain = " → ".join(str(f.name) for f in import_stack + [file_path])
        raise CircularImportError(f"Circular import detected: {chain}")

    data = _load_yaml(file_path)
    import_stack = import_stack + [file_path]

    # Imported tasks merge in first; local tasks would win a key collision,
    # though namespacing makes one impossible (imported keys always contain
    # a dot, local names never do).
    merged_tasks: dict[str, Any] = {}

    imports = data.pop("imports", None) or []
    for import_spec in imports:
        child_file = import_spec["file"]
        child_namespace = import_spec["as"]

        full_namespace = (
            f"{namespace}.{child_namespace}" if namespace else child_namespace
        )

        # Import paths resolve relative to the importing file's directory
        child_path = file_path.parent / child_file
        if not child_path.exists():
            raise FileNotFoundError(f"Import file not found: {child_path}")

        child = _merge_file(child_path, full_namespace, import_stack)
        merged_tasks.update(child.get("tasks") or {})

    local_tasks = data.get("tasks") or {}
    if namespace:
        local_tasks = {
            f"{namespace}.{name}": task for name, task in local_tasks.items()
        }
    merged_tasks.update(local_tasks)

    if merged_tasks or "tasks" in data:
        data["tasks"] = merged_tasks

    return data


def _load_yaml(file_path: Path) -> dict[str, Any]:
    # Explicit UTF-8 to handle Unicode on Windows (default is cp1252 there)
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}
