"""
Ordering for the references a task makes to its own inputs and outputs.

A pattern may name another of the task's patterns --
``inputs: [{src: a.txt}, {backup: "{{ self.inputs.src }}.bak"}]`` -- so the
patterns cannot all be rendered at once: each has to wait for the ones it
names. By the time patterns are rendered the invocation's arguments are
known, so the only ordering needed is between the patterns themselves, and
the only thing that can go wrong is a loop.

This module decides that order and nothing else. It is handed a render
callback because rendering belongs to the executor, which knows the rest of
the namespaces.
"""

from collections.abc import Callable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from typing import Any

from tasktree.template_refs import collect_template_refs


@dataclass(frozen=True)
class _Slot:
    """
    One pattern of a task, and how a self-reference would name it.

    ``position`` counts paths rather than YAML entries, matching the
    indexed view ``Task.__post_init__`` builds: a positional reference
    counts every path in declaration order, named or not.
    """

    field: str  # "inputs" or "outputs"
    position: int
    name: str | None
    text: Any

    @property
    def key(self) -> str:
        """How this slot reads in an error message."""
        return f"self.{self.field}.{self.name if self.name else self.position}"

    def aliases(self) -> tuple[str, ...]:
        """The reference forms that resolve to this slot."""
        positional = f"{self.field}.{self.position}"
        if self.name is None:
            return (positional,)
        return (positional, f"{self.field}.{self.name}")


def _slots_of(field: str, patterns: list) -> list[_Slot]:
    """
    Flatten one of a task's pattern lists into addressable slots.

    A named entry is a ``{name: path}`` dict and an anonymous one is the
    path itself; either way each path gets the next position.
    """
    slots = []
    for pattern in patterns:
        if isinstance(pattern, dict):
            for name, text in pattern.items():
                slots.append(_Slot(field, len(slots), name, text))
        else:
            slots.append(_Slot(field, len(slots), None, pattern))
    return slots


def _dependencies(slot: _Slot, by_alias: dict[str, _Slot]) -> set[_Slot]:
    """
    The slots this one names.

    A reference to something the task does not have yields no edge: the
    render reports it, with the list of names that do exist, which is a
    better error than anything this module could give.
    """
    if not isinstance(slot.text, str):
        return set()
    return {
        by_alias[reference]
        for reference in collect_template_refs(slot.text)["self"]
        if reference in by_alias
    }


def _cycle_message(task_name: str, cycle: list) -> str:
    loop = " -> ".join(slot.key for slot in cycle)
    return (
        f"Task '{task_name}': its inputs and outputs refer to each other in a "
        f"loop, so none of them can be resolved first: {loop}. "
        f"Break the loop by writing one of these paths out in full."
    )


def render_own_patterns(
    task_name: str,
    inputs: list,
    outputs: list,
    render: Callable[[str, dict[str, Any]], str],
) -> dict[str, Any]:
    """
    Render a task's own patterns, each after the ones it names.

    Args:
    task_name: Used in the error raised for a loop
    inputs: The task's raw ``inputs`` list
    outputs: The task's raw ``outputs`` list
    render: Renders one pattern, given the pattern and the self namespace
            built so far. Patterns resolved earlier in the order are
            already in that namespace; later ones are not, which is what
            makes the order matter.

    Returns:
    The keyword arguments build_task_config takes for the self namespace:
    ``inputs_named``, ``inputs_indexed``, ``outputs_named``,
    ``outputs_indexed``. Indexed entries keep declaration order.

    Raises:
    ValueError: If the patterns refer to each other in a loop
    """
    slots = _slots_of("inputs", inputs) + _slots_of("outputs", outputs)

    by_alias: dict[str, _Slot] = {}
    for slot in slots:
        for alias in slot.aliases():
            by_alias[alias] = slot

    sorter = TopologicalSorter({slot: _dependencies(slot, by_alias) for slot in slots})
    try:
        order = list(sorter.static_order())
    except CycleError as e:
        raise ValueError(_cycle_message(task_name, e.args[1]))

    # Indexed entries are addressed by position, and the order patterns
    # resolve in is not the order they were declared in, so each list is
    # sized up front and filled in place.
    resolved: dict[str, Any] = {
        "inputs_named": {},
        "inputs_indexed": [None] * sum(1 for slot in slots if slot.field == "inputs"),
        "outputs_named": {},
        "outputs_indexed": [None] * sum(1 for slot in slots if slot.field == "outputs"),
    }

    for slot in order:
        value = render(slot.text, resolved) if isinstance(slot.text, str) else slot.text
        resolved[f"{slot.field}_indexed"][slot.position] = value
        if slot.name is not None:
            resolved[f"{slot.field}_named"][slot.name] = value

    return resolved
