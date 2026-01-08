import hashlib
import json
from typing import Any, Optional


def _arg_sort_key(arg: str | dict[str, Any]) -> str:
    """Extract the sort key from an arg for deterministic hashing.

    Args:
        arg: Either a string arg or dict arg specification

    Returns:
        The argument name to use as a sort key
    """
    if isinstance(arg, dict):
        # Dict args have exactly one key - the argument name
        # This is validated by parse_arg_spec in parser.py
        return next(iter(arg.keys()))
    return arg


def _normalize_choices_lists(args: list[str | dict[str, Any]]) ->  list[str | dict[str, Any]]:
    normalized_args = []
    for arg in args:
        if isinstance(arg, dict):
            # Deep copy and sort choices if present
            normalized = {}
            for key, value in arg.items():
                if isinstance(value, dict) and 'choices' in value:
                    normalized[key] = {**value, 'choices': sorted(value['choices'], key=str)}
                else:
                    normalized[key] = value
            normalized_args.append(normalized)
        else:
            normalized_args.append(arg)

    return normalized_args


def _serialize_outputs_for_hash(outputs: list[str | dict[str, str]]) -> list[str]:
    """Serialize outputs to consistent list of strings for hashing.

    Converts both named outputs (dicts) and anonymous outputs (strings)
    into a consistent, sortable format.

    Args:
        outputs: List of output specifications (strings or dicts)

    Returns:
        List of serialized output strings in sorted order

    Example:
        >>> _serialize_outputs_for_hash(["file.txt", {"bundle": "app.js"}])
        ['bundle:app.js', 'file.txt']
    """
    serialized = []
    for output in outputs:
        if isinstance(output, str):
            # Anonymous output: just the path
            serialized.append(output)
        elif isinstance(output, dict):
            # Named output: serialize as "name:path" for each entry
            # Sort dict items for consistent ordering
            for name, path in sorted(output.items()):
                serialized.append(f"{name}:{path}")
    return sorted(serialized)


def hash_task(
    cmd: str,
    outputs: list[str | dict[str, str]],
    working_dir: str,
    args: list[str | dict[str, Any]],
    env: str = "",
    deps: list[str | dict[str, Any]] | None = None
) -> str:
    """Hash task definition including dependencies.

    Args:
        cmd: Task command
        outputs: Task outputs (strings or named dicts)
        working_dir: Working directory
        args: Task argument specifications
        env: Environment name
        deps: Dependency specifications (optional, for dependency hash)

    Returns:
        8-character hash of task definition
    """
    data = {
        "cmd": cmd,
        "outputs": _serialize_outputs_for_hash(outputs),
        "working_dir": working_dir,
        "args": sorted(_normalize_choices_lists(args), key=_arg_sort_key),
        "env": env,
    }

    # Include dependency invocation signatures if provided
    if deps is not None:
        # Normalize deps for hashing using JSON serialization for consistency
        normalized_deps = []
        for dep in deps:
            if isinstance(dep, str):
                # Simple string dependency
                normalized_deps.append(dep)
            elif isinstance(dep, dict):
                # Dict dependency with args - normalize to canonical form
                # Sort the dict to ensure consistent hashing
                normalized_deps.append(dict(sorted(dep.items())))
            else:
                normalized_deps.append(dep)
        # Sort using JSON serialization for consistent ordering
        data["deps"] = sorted(normalized_deps, key=lambda x: json.dumps(x, sort_keys=True) if isinstance(x, dict) else x)

    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def hash_args(args_dict: dict[str, Any]) -> str:
    serialized = json.dumps(args_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]


def hash_environment_definition(env) -> str:
    """Hash environment definition fields that affect task execution.

    Args:
        env: Environment to hash

    Returns:
        16-character hash of environment definition
    """
    # Import inside function to avoid circular dependency
    from tasktree.parser import Environment

    # Handle args - can be list (shell args) or dict (docker build args)
    args_value = env.args
    if isinstance(env.args, dict):
        args_value = dict(sorted(env.args.items()))  # Sort dict for determinism
    elif isinstance(env.args, list):
        args_value = sorted(env.args)  # Sort list for determinism

    data = {
        "shell": env.shell,
        "args": args_value,
        "preamble": env.preamble,
        "dockerfile": env.dockerfile,
        "context": env.context,
        "volumes": sorted(env.volumes),
        "ports": sorted(env.ports),
        "env_vars": dict(sorted(env.env_vars.items())),
        "working_dir": env.working_dir,
    }
    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def make_cache_key(task_hash: str, args_hash: Optional[str] = None) -> str:
    if args_hash:
        return f"{task_hash}__{args_hash}"
    return task_hash
