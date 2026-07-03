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
    _extract_from_string(node, refs)
    return refs


def _extract_from_string(text: Any, refs: dict[str, set[str]]) -> None:
    if not isinstance(text, str):
        return
    for block in _TEMPLATE_BLOCK.findall(text):
        for match in _REFERENCE.finditer(block):
            refs[match.group(1)].add(match.group(2))
