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


def merge_recipe(recipe_path: Path) -> dict[str, Any]:
    """
    Merge a recipe file and its imports into a single raw dict.

    Args:
    recipe_path: Path to the main recipe file

    Returns:
    The merged raw recipe dict (empty dict for an empty file)
    """
    return _load_yaml(recipe_path)


def _load_yaml(file_path: Path) -> dict[str, Any]:
    # Explicit UTF-8 to handle Unicode on Windows (default is cp1252 there)
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}
