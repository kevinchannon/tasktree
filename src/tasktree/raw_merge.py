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
    blanket_runner: str = "",
) -> dict[str, Any]:
    """
    Load one file and fold its imports in, applying namespace transforms.

    Args:
    file_path: Path to the YAML file
    namespace: Full namespace chain for this file (None for the root file)
    import_stack: Files currently being imported (for circular detection)
    blanket_runner: run_in override to apply to this file's own non-pinned,
    runnerless tasks (does not cascade into this file's imports - each
    import spec carries its own run_in)
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
    merged_runners: dict[str, Any] = {}

    # The 'as' names of this file's own imports, for dependency rewriting:
    # a dotted dep whose root segment is one of these is a local reference
    # (gets this file's namespace prefix); any other dotted dep is an
    # absolute reference into another part of the tree and stays as-is.
    local_import_namespaces: set[str] = set()

    imports = data.pop("imports", None) or []
    for import_spec in imports:
        child_file = import_spec["file"]
        child_namespace = import_spec["as"]
        local_import_namespaces.add(child_namespace)

        full_namespace = (
            f"{namespace}.{child_namespace}" if namespace else child_namespace
        )

        # Import paths resolve relative to the importing file's directory
        child_path = file_path.parent / child_file
        if not child_path.exists():
            raise FileNotFoundError(f"Import file not found: {child_path}")

        child = _merge_file(
            child_path,
            full_namespace,
            import_stack,
            import_spec.get("run_in", ""),
        )
        merged_tasks.update(child.get("tasks") or {})

        # Selective runner import: only runners referenced by pinned tasks
        # come along. Non-pinned imported tasks are expected to use the
        # run_in blanket (or the root default); pinning is the explicit
        # opt-in that brings a task's own runner with it.
        pinned_runner_names = {
            task["runner"]
            for task in (child.get("tasks") or {}).values()
            if isinstance(task, dict)
            and task.get("pin_runner")
            and isinstance(task.get("runner"), str)
            and task["runner"]
        }
        child_runners = child.get("runners")
        if isinstance(child_runners, dict):
            merged_runners.update(
                {
                    name: config
                    for name, config in child_runners.items()
                    if name in pinned_runner_names
                }
            )

    local_tasks = data.get("tasks") or {}
    if namespace:
        for task in local_tasks.values():
            if not isinstance(task, dict):
                continue
            if "deps" in task:
                task["deps"] = _rewrite_deps(
                    task["deps"], namespace, local_import_namespaces
                )
            _apply_runner_transforms(task, namespace, blanket_runner)
        local_tasks = {
            f"{namespace}.{name}": task for name, task in local_tasks.items()
        }
    merged_tasks.update(local_tasks)

    if merged_tasks or "tasks" in data:
        data["tasks"] = merged_tasks

    local_runners = data.get("runners")
    if isinstance(local_runners, dict):
        if namespace:
            # Imported 'default' declarations are dropped: only the root
            # file's default runner applies to the merged recipe.
            local_runners = {
                f"{namespace}.{name}": config
                for name, config in local_runners.items()
                if name != "default"
            }
        merged_runners.update(local_runners)
        data["runners"] = merged_runners
    elif merged_runners:
        # No usable local section; a null/missing one gains the imported
        # runners, anything else is left for validation to reject.
        if local_runners is None:
            data["runners"] = merged_runners

    return data


def _rewrite_deps(
    deps: Any, namespace: str, local_import_namespaces: set[str]
) -> Any:
    """Namespace the dependency names of one imported task."""
    if isinstance(deps, str):
        deps = [deps]
    if not isinstance(deps, list):
        return deps
    rewritten: list[Any] = []
    for dep in deps:
        if isinstance(dep, str):
            rewritten.append(
                _rewrite_dep_name(dep, namespace, local_import_namespaces)
            )
        elif isinstance(dep, dict):
            # Parameterized dep: {task-name: args} - rewrite the name only
            rewritten.append(
                {
                    _rewrite_dep_name(name, namespace, local_import_namespaces): args
                    for name, args in dep.items()
                }
            )
        else:
            rewritten.append(dep)
    return rewritten


def _apply_runner_transforms(
    task: dict[str, Any], namespace: str, blanket_runner: str
) -> None:
    """
    Namespace an imported task's runner name and apply the run_in blanket.

    A named runner is always prefixed (runner names in an imported file can
    only refer to that file's own runners). Inline definition dicts pass
    through untouched. The blanket applies only to non-pinned tasks with no
    runner at all - a name or an inline definition both count as explicit.
    """
    runner_value = task.get("runner", "")
    if not isinstance(runner_value, str):
        # Inline definition dicts pass through; invalid values are left for
        # validation to reject rather than being masked by the blanket
        return
    if runner_value:
        task["runner"] = f"{namespace}.{runner_value}"
    elif blanket_runner and not task.get("pin_runner"):
        task["runner"] = blanket_runner


def _rewrite_dep_name(
    name: str, namespace: str, local_import_namespaces: set[str]
) -> str:
    root_segment = name.split(".", 1)[0]
    if "." not in name or root_segment in local_import_namespaces:
        return f"{namespace}.{name}"
    return name


def _load_yaml(file_path: Path) -> dict[str, Any]:
    # Explicit UTF-8 to handle Unicode on Windows (default is cp1252 there)
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else {}
