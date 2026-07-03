"""
Generic discovery of template references in raw recipe subtrees.

collect_template_refs walks every string in a dict/list subtree and extracts
the ``{{ prefix.name }}`` references it finds, grouped by prefix. It serves
pruning (which variables to evaluate), hashing (which values to fold into the
task hash) and the runner variable-class restriction — one shared
implementation so those consumers cannot disagree about what a subtree
references.

Extraction is regex-based and deliberately biased toward over-matching:
evaluating an extra variable is harmless, while missing one breaks rendering
or hashing.
"""

import re
from typing import Any

TEMPLATE_PREFIXES = ("var", "arg", "env", "tt", "dep", "self")

_TEMPLATE_BLOCK = re.compile(r"\{\{.*?}}", re.DOTALL)
_REFERENCE = re.compile(
    r"\b(var|arg|env|tt|dep|self)\s*\.\s*"
    r"([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)"
)


def collect_template_refs(node: Any) -> dict[str, set[str]]:
    """
    Collect every template reference in a raw recipe subtree.

    Args:
    node: Any node of a parsed-YAML tree (str, dict, list or scalar)

    Returns:
    Mapping of prefix -> set of referenced names, with a (possibly empty)
    entry for every prefix in TEMPLATE_PREFIXES. Names keep their full
    dotted form after the prefix (e.g. ``dep.build.outputs.bin`` yields
    ``build.outputs.bin`` under ``dep``).
    """
    refs: dict[str, set[str]] = {prefix: set() for prefix in TEMPLATE_PREFIXES}
    _walk(node, refs)
    return refs


def expand_variable_refs(
    refs: dict[str, set[str]], raw_variables: dict[str, Any]
) -> dict[str, set[str]]:
    """
    Expand collected refs with the transitive closure over variable definitions.

    A referenced variable's definition may itself reference other variables
    (``var.a: "{{ var.b }}"``), so consumers that need *everything* a subtree
    depends on must chase definitions to a fixpoint. Names with no definition
    in raw_variables are kept but not chased — discovery is not validation.

    Args:
    refs: Mapping as returned by collect_template_refs
    raw_variables: The recipe's raw ``variables`` section

    Returns:
    A new mapping of the same shape, a superset of refs.
    """
    expanded = {prefix: set(refs.get(prefix, ())) for prefix in TEMPLATE_PREFIXES}
    pending = list(expanded["var"])
    chased: set[str] = set()
    while pending:
        name = pending.pop()
        if name in chased:
            continue
        chased.add(name)
        definition = raw_variables.get(name)
        definition_refs = collect_template_refs(definition)
        # The { env: NAME } definition form names its env var as a bare
        # string, not a {{ env.NAME }} template, so the walker cannot see it.
        if isinstance(definition, dict) and isinstance(definition.get("env"), str):
            definition_refs["env"].add(definition["env"])
        for prefix in TEMPLATE_PREFIXES:
            expanded[prefix] |= definition_refs[prefix]
        pending.extend(definition_refs["var"])
    return expanded


def _walk(node: Any, refs: dict[str, set[str]]) -> None:
    if isinstance(node, str):
        _extract_from_string(node, refs)
    elif isinstance(node, dict):
        for key, value in node.items():
            _walk(key, refs)
            _walk(value, refs)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _walk(item, refs)


def _extract_from_string(text: str, refs: dict[str, set[str]]) -> None:
    for block in _TEMPLATE_BLOCK.findall(text):
        for match in _REFERENCE.finditer(block):
            refs[match.group(1)].add(match.group(2))
