"""
Raw-dict import merging for the schema-validation pipeline (issue #43, slice 4).

Merges a recipe file and all of its imports into a single raw dict *before*
any Task/Runner object is constructed. Namespacing, run_in blanket overrides
and pinned-runner rewrites are applied as dict transforms, so the result is
what the runtime schema validation (slice 6) will validate. Built additively
alongside the object-building path in parser.py; sections cut over one at a
time.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Rewrites {{ var.X }} to {{ var.<namespace>.X }} (captures the surrounding
# delimiters so the substitution can re-emit them)
VAR_REFERENCE_REWRITE_PATTERN = re.compile(r"(\{\{\s*var\.)([^\s}]+)(\s*}})")


class CircularImportError(Exception):
    """
    Raised when a circular import is detected.
    """

    pass


def local_name_error(name: str, kind: str) -> str | None:
    """Return an error message if a local item name is invalid, None otherwise."""
    if not name:
        return f"{kind} name must not be empty"
    if "." in name:
        return f"{kind} name '{name}' must not contain dots (reserved for import namespacing)"
    return None


@dataclass
class MergedRecipe:
    """A merged raw recipe tree plus deferred name-validation errors."""

    data: dict[str, Any]
    # Keyed by the item's merged (namespaced) name; surfaced later, only if
    # the item turns out to be reachable
    name_errors: dict[str, str] = field(default_factory=dict)
    # Merged task name -> path of the file that defined it (user-visible
    # via Task.source_file / tt --show)
    task_sources: dict[str, str] = field(default_factory=dict)


def merge_recipe_files(recipe_path: Path) -> MergedRecipe:
    """
    Merge a recipe file and its imports into a single raw dict.

    The 'imports' key is consumed by the merge and never appears in the
    result (its presence downstream would indicate a merge bug). Invalid
    local names (dots, empty) for runners/interpreters/variables are not
    raised here but recorded as deferred name errors, keyed by merged name.

    Args:
    recipe_path: Path to the main recipe file

    Returns:
    MergedRecipe with the merged tree (empty dict for an empty file) and
    any deferred name errors

    Raises:
    FileNotFoundError: If an imported file doesn't exist
    CircularImportError: If a circular import is detected
    """
    name_errors: dict[str, str] = {}
    task_sources: dict[str, str] = {}
    data = _merge_file(
        recipe_path,
        namespace=None,
        import_stack=[],
        name_errors=name_errors,
        task_sources=task_sources,
    )
    return MergedRecipe(data=data, name_errors=name_errors, task_sources=task_sources)


def merge_recipe(recipe_path: Path) -> dict[str, Any]:
    """The merged tree only - see merge_recipe_files."""
    return merge_recipe_files(recipe_path).data


def _merge_file(
    file_path: Path,
    namespace: str | None,
    import_stack: list[Path],
    blanket_runner: str = "",
    *,
    name_errors: dict[str, str],
    task_sources: dict[str, str],
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
    merged_variables: dict[str, Any] = {}
    merged_interpreters: dict[str, Any] = {}

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
            name_errors=name_errors,
            task_sources=task_sources,
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

        child_variables = child.get("variables")
        if isinstance(child_variables, dict):
            merged_variables.update(child_variables)

        child_interpreters = child.get("interpreters")
        if isinstance(child_interpreters, dict):
            merged_interpreters.update(child_interpreters)

    _validate_top_level_keys(data, file_path)

    local_tasks = data.get("tasks") or {}
    if isinstance(local_tasks, dict):
        # Unlike runner/variable/interpreter names (deferred until the item
        # proves reachable), an invalid task name raises immediately -
        # parity with the old object path.
        for name in local_tasks:
            error = local_name_error(name, "Task")
            if error:
                raise ValueError(error)
    if namespace:
        local_tasks = _namespace_var_refs(local_tasks, namespace)
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
    for name in local_tasks:
        task_sources[name] = str(file_path)
    merged_tasks.update(local_tasks)

    if merged_tasks or "tasks" in data:
        data["tasks"] = merged_tasks

    local_runners = data.get("runners")
    if isinstance(local_runners, dict):
        _record_name_errors(
            local_runners, "Runner", namespace, name_errors, skip={"default"}
        )
        if namespace:
            # Imported 'default' declarations are dropped: only the root
            # file's default runner applies to the merged recipe.
            local_runners = {
                f"{namespace}.{name}": _namespace_interpreter_use(
                    _namespace_var_refs(config, namespace), namespace
                )
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

    local_variables = data.get("variables")
    if isinstance(local_variables, dict):
        _record_name_errors(local_variables, "Variable", namespace, name_errors)
        if namespace:
            local_variables = {
                f"{namespace}.{name}": _namespace_var_refs(value, namespace)
                for name, value in local_variables.items()
            }
        merged_variables.update(local_variables)
        data["variables"] = merged_variables
    elif merged_variables:
        if local_variables is None:
            data["variables"] = merged_variables

    # Imported interpreters are merged (namespaced) so that imported pinned
    # runners' 'use:' references stay resolvable in the merged tree. The old
    # object path resolved those references during the import and then threw
    # the imported interpreters away. Task-level interpreter names are NOT
    # namespaced - they resolve against the root registry, as before.
    local_interpreters = data.get("interpreters")
    if isinstance(local_interpreters, dict):
        _record_name_errors(
            local_interpreters, "Interpreter", namespace, name_errors, skip={"default"}
        )
        if namespace:
            local_interpreters = {
                f"{namespace}.{name}": _namespace_var_refs(value, namespace)
                for name, value in local_interpreters.items()
                if name != "default"
            }
        merged_interpreters.update(local_interpreters)
        data["interpreters"] = merged_interpreters
    elif merged_interpreters:
        if local_interpreters is None:
            data["interpreters"] = merged_interpreters

    return data


def collect_reachable_task_names(tasks_data: dict[str, Any], root: str) -> set[str]:
    """
    Collect the task names reachable from root via deps, on the raw dict.

    Runs on unvalidated data (pruning happens before validation), so it is
    deliberately tolerant: a non-dict task is a leaf, deps of unexpected
    shape contribute nothing, and nonexistent dep names stay in the result
    so graph construction can report them. Shape errors surface later, from
    task construction or the dependency graph - never from here.

    Args:
    tasks_data: The merged tree's 'tasks' section
    root: Name of the invoked task (caller checks it exists)

    Returns:
    Set of reachable task names, including root and any missing dep names
    """
    reachable: set[str] = set()
    queue = [root]

    while queue:
        name = queue.pop()
        if name in reachable:
            continue
        reachable.add(name)
        task_data = tasks_data.get(name)
        if not isinstance(task_data, dict):
            continue

        deps = task_data.get("deps", [])
        if isinstance(deps, str):
            deps = [deps]
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if isinstance(dep, str):
                queue.append(dep)
            elif isinstance(dep, dict) and len(dep) == 1:
                dep_name = next(iter(dep))
                if isinstance(dep_name, str):
                    queue.append(dep_name)

    return reachable


def _validate_top_level_keys(data: dict[str, Any], file_path: Path) -> None:
    """
    Reject unknown top-level keys in one file, with a 'tasks:' hint when the
    file looks like task definitions written at the root level.

    Runs per file during the merge (the merged tree can't be checked - it no
    longer knows which file an offending key came from). Wording matches the
    old object path until slice 6/8 replaces this with the schema.
    """
    valid_top_level_keys = {"imports", "runners", "interpreters", "tasks", "variables"}

    # Check if tasks key is missing when there appear to be task definitions
    # at root level, BEFORE checking for unknown keys, for the better message
    if "tasks" not in data and data:
        potential_tasks = [
            k
            for k, v in data.items()
            if isinstance(v, dict) and k not in valid_top_level_keys
        ]

        if potential_tasks:
            raise ValueError(
                f"Invalid recipe format in {file_path}\n\n"
                f"Task definitions must be under a top-level 'tasks:' key.\n\n"
                f"Found these keys at root level: {', '.join(potential_tasks)}\n\n"
                f"Did you mean:\n\n"
                f"tasks:\n"
                + "\n".join(f"  {k}:" for k in potential_tasks)
                + "\n    cmd: ...\n\n"
                f"Valid top-level keys are: {', '.join(sorted(valid_top_level_keys))}"
            )

    invalid_keys = set(data.keys()) - valid_top_level_keys
    if invalid_keys:
        raise ValueError(
            f"Invalid recipe format in {file_path}\n\n"
            f"Unknown top-level keys: {', '.join(sorted(invalid_keys))}\n\n"
            f"Valid top-level keys are:\n"
            f"  - imports      (for importing task files)\n"
            f"  - runners      (for runner configuration)\n"
            f"  - interpreters (for interpreter definitions)\n"
            f"  - variables    (for variable definitions)\n"
            f"  - tasks        (for task definitions)"
        )


def _record_name_errors(
    section: dict[str, Any],
    kind: str,
    namespace: str | None,
    name_errors: dict[str, str],
    skip: frozenset[str] | set[str] = frozenset(),
) -> None:
    """
    Record deferred errors for invalid local names in one file's section.

    Errors are keyed by the merged (namespaced) name so reachability checks
    can look them up later; the message names the local (pre-namespace)
    item, matching the object path's wording.
    """
    for name in section:
        if name in skip:
            continue
        error = local_name_error(name, kind)
        if error:
            merged_name = f"{namespace}.{name}" if namespace else name
            name_errors[merged_name] = error


def _namespace_interpreter_use(config: Any, namespace: str) -> Any:
    """
    Prefix a runner definition's interpreter {use: name} reference.

    A runner in an imported file resolves 'use:' against that file's own
    interpreters section, whose names gain the namespace prefix on merge -
    so the reference must gain it too. String shorthands and inline
    definitions name no interpreter and pass through.
    """
    if not isinstance(config, dict):
        return config
    interpreter = config.get("interpreter")
    if isinstance(interpreter, dict) and isinstance(interpreter.get("use"), str):
        return {
            **config,
            "interpreter": {
                **interpreter,
                "use": f"{namespace}.{interpreter['use']}",
            },
        }
    return config


def _namespace_var_refs(node: Any, namespace: str) -> Any:
    """
    Rewrite {{ var.X }} to {{ var.<namespace>.X }} in every string of a tree.

    Walks values only (dict keys are section/item names, never templates).
    Deliberately broader than the old per-field rewrite in parser.py: any
    string anywhere in an imported definition gets its variable references
    namespaced, so fields the old path missed (dependency argument
    templates, inline runner definitions) can't refer to the wrong scope.
    """
    if isinstance(node, str):
        return VAR_REFERENCE_REWRITE_PATTERN.sub(
            rf"\g<1>{namespace}.\2\3", node
        )
    if isinstance(node, list):
        return [_namespace_var_refs(item, namespace) for item in node]
    if isinstance(node, dict):
        return {
            key: _namespace_var_refs(value, namespace)
            for key, value in node.items()
        }
    return node


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
