"""
Build the per-task configuration object used for template rendering.

This is the "evaluate variables" stage (stage 2 of the rendering pipeline):
once the reachable tasks are known, the values needed for substitution are
gathered into a single context object keyed by namespace (var, arg, env, tt,
and later dep/self). That object is then handed to ``rendering.render`` to
produce the final task definition.

Keeping this assembly in a pure function lets the variable-evaluation stage be
tested independently of resolution and rendering.
"""

import os
from collections.abc import Mapping
from typing import Any


class _OutputsNamespace(dict):
    """
    The ``outputs`` map for one dependency task.

    Raises an actionable error when a template references an output name that the
    dependency task does not define.
    """

    def __init__(self, dep_task_name: str, outputs: Mapping[str, str]):
        super().__init__(outputs)
        self._dep_task_name = dep_task_name

    def __missing__(self, key: str) -> Any:
        available = ", ".join(self.keys()) if self else "(none)"
        raise ValueError(
            f"Dependency '{self._dep_task_name}' has no output named '{key}'.\n"
            f"Available named outputs in '{self._dep_task_name}': {available}"
        )


class _DepNamespace(dict):
    """
    The ``dep`` namespace.

    Maps a dependency task name to an object exposing its ``outputs``. Raises an
    actionable error when a template references a task that is not a dependency
    of the current task (or that exposes no named outputs).
    """

    def __missing__(self, key: str) -> Any:
        available = ", ".join(self.keys()) if self else "(none)"
        raise ValueError(
            f"'{key}' is not a dependency of this task (or exposes no named "
            f"outputs).\n"
            f"Available dependencies with named outputs: {available}"
        )


class _ArgNamespace(dict):
    """
    The ``arg`` namespace.

    Behaves like a plain dict for regular arguments, but raises an actionable
    error when a template references an *exported* argument. Exported arguments
    are only available to commands as ``$NAME`` environment variables, never via
    ``{{ arg.name }}`` substitution.
    """

    def __init__(self, values: Mapping[str, Any], exported_names: set[str]):
        super().__init__(values)
        self._exported_names = set(exported_names)

    def __missing__(self, key: str) -> Any:
        if key in self._exported_names:
            raise ValueError(
                f"Argument '{key}' is exported (defined as ${key}) and cannot be "
                f"used in template substitution.\n"
                f"Exported arguments are available to commands as environment "
                f"variables: ${key}"
            )
        raise KeyError(key)


def build_task_config(
    *,
    variables: Mapping[str, str] | None = None,
    args: Mapping[str, Any] | None = None,
    exported_args: set[str] | None = None,
    builtins: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
    dep_outputs: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Assemble the rendering context for a single task.

    Args:
    variables: Evaluated recipe variables (the ``var`` namespace)
    args: Regular (non-exported) argument values (the ``arg`` namespace)
    exported_args: Names of exported arguments; referencing one in a template
    raises an actionable error rather than substituting a value
    builtins: Built-in variable values (the ``tt`` namespace)
    env: Environment variables (the ``env`` namespace); defaults to a snapshot
    of ``os.environ``
    dep_outputs: Named outputs of dependency tasks, keyed by task name then
    output name (the ``dep`` namespace)

    Returns:
    A context dict with ``var``, ``arg``, ``env``, ``tt`` and ``dep`` keys
    suitable for passing to ``rendering.render``.
    """
    env_snapshot = dict(env) if env is not None else dict(os.environ)

    dep_namespace = _DepNamespace(
        {
            task_name: {"outputs": _OutputsNamespace(task_name, outputs)}
            for task_name, outputs in (dep_outputs or {}).items()
        }
    )

    return {
        "var": dict(variables or {}),
        "arg": _ArgNamespace(args or {}, exported_args or set()),
        "env": env_snapshot,
        "tt": dict(builtins or {}),
        "dep": dep_namespace,
    }
