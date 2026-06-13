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
from collections.abc import Mapping, Sequence
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


class _EnvNamespace(dict):
    """
    The ``env`` namespace.

    Raises an actionable error when a template references an environment variable
    that is not set, matching the wording users rely on.
    """

    def __missing__(self, key: str) -> Any:
        raise ValueError(f"Environment variable '{key}' is not set")


class _FieldNamespace:
    """
    The ``self.inputs`` or ``self.outputs`` namespace for the current task.

    Supports both named access (``{{ self.inputs.src }}``) via the named map and
    positional access (``{{ self.inputs.0 }}``) via the indexed list, which
    includes anonymous entries in YAML declaration order.
    """

    def __init__(
        self,
        task_name: str,
        field: str,
        named: Mapping[str, str],
        indexed: Sequence[str],
    ):
        self._task_name = task_name
        self._field = field  # "inputs" or "outputs"
        self._named = dict(named)
        self._indexed = list(indexed)

    @property
    def _singular(self) -> str:
        return "input" if self._field == "inputs" else "output"

    def __getitem__(self, key: Any) -> str:
        if isinstance(key, int):
            return self._positional(key)
        return self._by_name(str(key))

    def _positional(self, index: int) -> str:
        if not self._indexed:
            raise ValueError(
                f"Task '{self._task_name}' references {self._singular} index "
                f"'{index}' but has no {self._field} defined"
            )
        if index >= len(self._indexed):
            max_index = len(self._indexed) - 1
            raise ValueError(
                f"Task '{self._task_name}' references {self._singular} index "
                f"'{index}' but only has {len(self._indexed)} {self._field} "
                f"(indices 0-{max_index})"
            )
        return self._indexed[index]

    def _by_name(self, name: str) -> str:
        if name not in self._named:
            available = ", ".join(self._named) if self._named else "(none)"
            raise ValueError(
                f"Task '{self._task_name}' references {self._singular} '{name}' "
                f"but has no {self._singular} named '{name}'.\n"
                f"Available named {self._field}: {available}"
            )
        return self._named[name]


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
    task_name: str = "",
    inputs_named: Mapping[str, str] | None = None,
    inputs_indexed: Sequence[str] | None = None,
    outputs_named: Mapping[str, str] | None = None,
    outputs_indexed: Sequence[str] | None = None,
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
    task_name: Name of the current task, used in ``self.*`` error messages
    inputs_named: Named inputs of the current task (``self.inputs.<name>``)
    inputs_indexed: All inputs in YAML order (``self.inputs.<index>``)
    outputs_named: Named outputs of the current task (``self.outputs.<name>``)
    outputs_indexed: All outputs in YAML order (``self.outputs.<index>``)

    Returns:
    A context dict with ``var``, ``arg``, ``env``, ``tt``, ``dep`` and ``self``
    keys suitable for passing to ``rendering.render``.
    """
    env_snapshot = _EnvNamespace(env if env is not None else os.environ)

    dep_namespace = _DepNamespace(
        {
            task_name: {"outputs": _OutputsNamespace(task_name, outputs)}
            for task_name, outputs in (dep_outputs or {}).items()
        }
    )

    self_namespace = {
        "inputs": _FieldNamespace(
            task_name, "inputs", inputs_named or {}, inputs_indexed or []
        ),
        "outputs": _FieldNamespace(
            task_name, "outputs", outputs_named or {}, outputs_indexed or []
        ),
    }

    return {
        "var": dict(variables or {}),
        "arg": _ArgNamespace(args or {}, exported_args or set()),
        "env": env_snapshot,
        "tt": dict(builtins or {}),
        "dep": dep_namespace,
        "self": self_namespace,
    }
