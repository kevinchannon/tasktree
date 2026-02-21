"""Tree-sitter based YAML context detection for the tasktree LSP server.

This module replaces the two-stage PyYAML-parse / regex-heuristic approach
with a single tree-sitter pipeline.  Tree-sitter is an incremental,
error-recovering parser: it always produces a concrete syntax tree, marking
invalid regions as ERROR nodes rather than aborting.  This gives consistent,
queryable structure regardless of document validity — essential for an LSP
that operates on documents that are almost always incomplete.

Public API
----------
parse_document(text)                   → Tree
get_task_at_position(tree, line, col)  → str | None
is_in_field(tree, line, col, name)     → bool
is_in_substitutable_field(tree, l, c)  → bool
extract_variables(tree)                → list[str]
extract_task_args(tree, task_name)     → list[str]
extract_task_inputs(tree, task_name)   → list[str]
extract_task_outputs(tree, task_name)  → list[str]
extract_task_names(tree, base_path)    → list[str]
"""

import logging
from pathlib import Path

import tree_sitter_yaml as tsyaml
from tree_sitter import Language, Node, Parser, Tree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level parser initialisation (shared across all calls)
# ---------------------------------------------------------------------------

_YAML_LANGUAGE = Language(tsyaml.language())
_parser = Parser(_YAML_LANGUAGE)

# ---------------------------------------------------------------------------
# Node-type sets (verified against tree-sitter-yaml 0.7.x grammar)
# ---------------------------------------------------------------------------

_PAIR_TYPES = frozenset({"block_mapping_pair", "flow_pair"})
_MAPPING_TYPES = frozenset({"block_mapping", "flow_mapping"})
_SEQUENCE_TYPES = frozenset({"block_sequence", "flow_sequence"})
# Punctuation tokens that appear as direct children of flow sequences
_FLOW_SEQ_PUNCT = frozenset({"[", "]", ","})

# Fields where {{ arg.* }} and {{ self.* }} substitutions are valid
_SUBSTITUTABLE_FIELDS = frozenset({"cmd", "working_dir", "outputs", "deps", "default"})


# ---------------------------------------------------------------------------
# Document parsing
# ---------------------------------------------------------------------------


def parse_document(text: str) -> Tree:
    """Parse YAML text with tree-sitter, always returning a Tree.

    Unlike PyYAML, tree-sitter never raises on invalid input.  ERROR nodes
    mark regions that could not be parsed, but the tree is always complete
    and traversable.

    Args:
        text: Raw YAML document text (may be incomplete or malformed).

    Returns:
        A tree_sitter.Tree for the document.
    """
    return _parser.parse(bytes(text, "utf-8"))


# ---------------------------------------------------------------------------
# Low-level node helpers
# ---------------------------------------------------------------------------


def _get_text(node: Node) -> str:
    """Return the decoded UTF-8 text of a leaf node."""
    if node is None:
        return ""
    raw = node.text
    if isinstance(raw, (bytes, bytearray)):
        return raw.decode("utf-8", errors="replace")
    return str(raw) if raw else ""


def _get_scalar_value(node: Node) -> str:
    """Extract a scalar string value from a node, descending if necessary.

    Handles:
    - ``string_scalar``         — raw unquoted text
    - ``double_quote_scalar``   — strip surrounding ``"``
    - ``single_quote_scalar``   — strip surrounding ``'``
    - ``plain_scalar``          — recurse to find ``string_scalar``
    - compound wrappers (``flow_node``, ``block_node``, …) — recurse

    Returns empty string if no scalar is found.
    """
    if node is None:
        return ""

    t = node.type

    if t == "string_scalar":
        return _get_text(node)

    if t == "double_quote_scalar":
        raw = _get_text(node)
        return raw[1:-1] if len(raw) >= 2 else raw

    if t == "single_quote_scalar":
        raw = _get_text(node)
        return raw[1:-1] if len(raw) >= 2 else raw

    # Recurse into compound / wrapper nodes
    for child in node.children:
        result = _get_scalar_value(child)
        if result:
            return result

    return ""


def _get_pair_key(pair_node: Node) -> str:
    """Return the key string of a ``block_mapping_pair`` or ``flow_pair``."""
    if pair_node.type not in _PAIR_TYPES:
        return ""
    if not pair_node.children:
        return ""
    return _get_scalar_value(pair_node.children[0])


def _get_pair_value_node(pair_node: Node) -> Node | None:
    """Return the value node of a ``block_mapping_pair`` or ``flow_pair``.

    Skips the key (first child) and any ``:`` separator token.
    """
    if pair_node.type not in _PAIR_TYPES:
        return None
    for child in pair_node.children[1:]:
        if child.type != ":":
            return child
    return None


def _iter_mapping_pairs(mapping_node: Node):
    """Yield all ``block_mapping_pair`` / ``flow_pair`` children."""
    if mapping_node is None:
        return
    for child in mapping_node.children:
        if child.type in _PAIR_TYPES:
            yield child


def _iter_sequence_items(sequence_node: Node):
    """Yield content items from a ``block_sequence`` or ``flow_sequence``.

    Skips punctuation tokens (``[``, ``]``, ``,``).
    For ``block_sequence``, children are ``block_sequence_item`` nodes.
    For ``flow_sequence``, children are ``flow_node`` values interleaved
    with punctuation.
    """
    if sequence_node is None:
        return
    for child in sequence_node.children:
        if child.type not in _FLOW_SEQ_PUNCT:
            yield child


def _find_mapping_in_node(node: Node) -> Node | None:
    """Find the first ``block_mapping`` or ``flow_mapping`` in a subtree."""
    if node is None:
        return None
    if node.type in _MAPPING_TYPES:
        return node
    for child in node.children:
        result = _find_mapping_in_node(child)
        if result is not None:
            return result
    return None


def _find_sequence_in_node(node: Node) -> Node | None:
    """Find the first ``block_sequence`` or ``flow_sequence`` in a subtree."""
    if node is None:
        return None
    if node.type in _SEQUENCE_TYPES:
        return node
    for child in node.children:
        result = _find_sequence_in_node(child)
        if result is not None:
            return result
    return None


def _item_to_scalar_or_mapping(item_node: Node):
    """Classify a sequence item as a string or a mapping.

    Returns:
        ``str``  — the scalar text if the item is a plain/anonymous value.
        ``Node`` — the mapping node if the item is a dict (named) value.
        ``None`` — if neither can be determined.
    """
    # Check for a nested mapping first (covers both block and flow dict items)
    mapping = _find_mapping_in_node(item_node)
    if mapping is not None:
        return mapping
    # Fall back to scalar text
    val = _get_scalar_value(item_node)
    return val if val else None


# ---------------------------------------------------------------------------
# Document-structure helpers
# ---------------------------------------------------------------------------


def _get_root_mapping(root_node: Node) -> Node | None:
    """Return the top-level mapping node of the document."""
    for child in root_node.children:
        if child.type == "document":
            result = _find_mapping_in_node(child)
            if result is not None:
                return result
    return _find_mapping_in_node(root_node)


def _find_section_value(root_node: Node, key: str) -> Node | None:
    """Return the value node for a top-level key (e.g. ``"tasks"``).

    Works for any value type (mapping, sequence, scalar).
    """
    root_mapping = _get_root_mapping(root_node)
    if root_mapping is None:
        return None
    for pair in _iter_mapping_pairs(root_mapping):
        if _get_pair_key(pair) == key:
            return _get_pair_value_node(pair)
    return None


def _find_section_mapping(root_node: Node, key: str) -> Node | None:
    """Return the mapping that is the value of a top-level key."""
    value = _find_section_value(root_node, key)
    return _find_mapping_in_node(value)


def _find_task_mapping(tree: Tree, task_name: str) -> Node | None:
    """Return the body mapping for a named task."""
    tasks_mapping = _find_section_mapping(tree.root_node, "tasks")
    if tasks_mapping is None:
        return None
    for pair in _iter_mapping_pairs(tasks_mapping):
        if _get_pair_key(pair) == task_name:
            value = _get_pair_value_node(pair)
            return _find_mapping_in_node(value)
    return None


def _find_field_value_in_mapping(
    task_mapping: Node, field_name: str
) -> Node | None:
    """Return the value node for a named field inside a task mapping."""
    if task_mapping is None:
        return None
    for pair in _iter_mapping_pairs(task_mapping):
        if _get_pair_key(pair) == field_name:
            return _get_pair_value_node(pair)
    return None


# ---------------------------------------------------------------------------
# Public API — position queries
# ---------------------------------------------------------------------------


def get_task_at_position(tree: Tree, line: int, col: int) -> str | None:
    """Find the task whose definition contains the cursor position.

    Uses the tree-sitter parse tree rather than regex heuristics.  Works
    with block-style, flow-style, and broken/incomplete YAML.

    The algorithm finds the task whose ``block_mapping_pair`` (or
    ``flow_pair``) in the ``tasks:`` mapping starts closest to — but not
    after — the cursor position.

    Args:
        tree:  Tree-sitter parse tree for the document.
        line:  Zero-based line index of the cursor.
        col:   Zero-based character index of the cursor.

    Returns:
        Task name string, or ``None`` if no task contains the position.
    """
    try:
        tasks_mapping = _find_section_mapping(tree.root_node, "tasks")
        if tasks_mapping is None:
            return None

        cursor_pt = (line, col)
        best_task: str | None = None
        best_start = (-1, -1)

        for pair in _iter_mapping_pairs(tasks_mapping):
            task_name = _get_pair_key(pair)
            if not task_name:
                continue
            pair_start = pair.start_point  # (row, col)
            if pair_start <= cursor_pt and pair_start > best_start:
                best_task = task_name
                best_start = pair_start

        return best_task
    except Exception as e:
        logger.debug("get_task_at_position failed: %s", e)
        return None


def is_in_field(tree: Tree, line: int, col: int, field_name: str) -> bool:
    """Return True if the cursor is inside the *value* of the named field.

    Walks up the ancestor chain from the deepest node at ``(line, col)``,
    looking for a mapping pair whose key matches ``field_name``.  The
    cursor must be in the value portion (after the key and colon) to
    return True.

    Works for both block-style and flow-style YAML, and for broken input
    where tree-sitter has created ERROR nodes.

    Args:
        tree:        Tree-sitter parse tree.
        line:        Zero-based line index.
        col:         Zero-based character index.
        field_name:  Key name to look for (e.g. ``"cmd"``).

    Returns:
        True if the cursor is in the value of the named field.
    """
    try:
        node = tree.root_node.descendant_for_point_range(
            (line, col), (line, col)
        )
        if node is None:
            return False

        current: Node | None = node
        while current is not None:
            if current.type in _PAIR_TYPES:
                key = _get_pair_key(current)
                if key == field_name:
                    # Cursor must be past the end of the key node
                    if current.children:
                        key_end = current.children[0].end_point
                        return (line, col) >= key_end
                    return False
            current = current.parent

        return False
    except Exception as e:
        logger.debug("is_in_field(%r) failed: %s", field_name, e)
        return False


def is_in_substitutable_field(tree: Tree, line: int, col: int) -> bool:
    """Return True if the cursor is in a field that supports substitutions.

    Substitution prefixes ``{{ arg.* }}``, ``{{ self.inputs.* }}``, and
    ``{{ self.outputs.* }}`` are valid in: ``cmd``, ``working_dir``,
    ``outputs``, ``deps``, and ``default`` (for args[].default).

    Args:
        tree: Tree-sitter parse tree.
        line: Zero-based line index.
        col:  Zero-based character index.

    Returns:
        True if the cursor is in a substitutable field.
    """
    try:
        node = tree.root_node.descendant_for_point_range(
            (line, col), (line, col)
        )
        if node is None:
            return False

        current: Node | None = node
        while current is not None:
            if current.type in _PAIR_TYPES:
                key = _get_pair_key(current)
                if key in _SUBSTITUTABLE_FIELDS:
                    if current.children:
                        key_end = current.children[0].end_point
                        if (line, col) >= key_end:
                            return True
            current = current.parent

        return False
    except Exception as e:
        logger.debug("is_in_substitutable_field failed: %s", e)
        return False


# ---------------------------------------------------------------------------
# Public API — identifier extraction
# ---------------------------------------------------------------------------


def extract_variables(tree: Tree) -> list[str]:
    """Extract variable names from the ``variables:`` section.

    Args:
        tree: Tree-sitter parse tree.

    Returns:
        Alphabetically sorted list of variable names, or empty list.
    """
    try:
        variables_mapping = _find_section_mapping(tree.root_node, "variables")
        if variables_mapping is None:
            return []
        names = []
        for pair in _iter_mapping_pairs(variables_mapping):
            name = _get_pair_key(pair)
            if name:
                names.append(name)
        return sorted(names)
    except Exception as e:
        logger.debug("extract_variables failed: %s", e)
        return []


def _extract_arg_names_from_sequence(sequence_node: Node) -> list[str]:
    """Extract arg names from a sequence node.

    - Plain string items (``- arg_name``) → the string is the arg name.
    - Dict items (``- arg_name: {…}``) → the first key is the arg name.
    """
    names = []
    for item in _iter_sequence_items(sequence_node):
        inner = _item_to_scalar_or_mapping(item)
        if isinstance(inner, str):
            if inner:
                names.append(inner)
        elif inner is not None:
            for pair in _iter_mapping_pairs(inner):
                name = _get_pair_key(pair)
                if name:
                    names.append(name)
                    break  # one key per arg item
    return names


def _extract_named_io_from_sequence(sequence_node: Node) -> list[str]:
    """Extract named input/output names from a sequence node.

    Only dict items are returned; plain string items (anonymous) are skipped.
    """
    names = []
    for item in _iter_sequence_items(sequence_node):
        inner = _item_to_scalar_or_mapping(item)
        if isinstance(inner, str):
            pass  # anonymous — skip
        elif inner is not None:
            for pair in _iter_mapping_pairs(inner):
                name = _get_pair_key(pair)
                if name:
                    names.append(name)
                    break
    return names


def extract_task_args(tree: Tree, task_name: str) -> list[str]:
    """Extract argument names for a specific task.

    Handles both the string format (``- arg_name``) and the dict format
    (``- arg_name: {type: str, default: value, …}``).

    Args:
        tree:      Tree-sitter parse tree.
        task_name: Name of the task to inspect.

    Returns:
        Alphabetically sorted list of arg names, or empty list.
    """
    try:
        task_mapping = _find_task_mapping(tree, task_name)
        if task_mapping is None:
            return []
        args_value = _find_field_value_in_mapping(task_mapping, "args")
        if args_value is None:
            return []
        sequence = _find_sequence_in_node(args_value)
        return sorted(_extract_arg_names_from_sequence(sequence))
    except Exception as e:
        logger.debug("extract_task_args(%r) failed: %s", task_name, e)
        return []


def extract_task_inputs(tree: Tree, task_name: str) -> list[str]:
    """Extract named input identifiers for a specific task.

    Only *named* inputs (dict items like ``- source: path/to/file``) are
    returned.  Anonymous inputs (plain strings) are skipped.

    Args:
        tree:      Tree-sitter parse tree.
        task_name: Name of the task to inspect.

    Returns:
        Alphabetically sorted list of named input identifiers.
    """
    try:
        task_mapping = _find_task_mapping(tree, task_name)
        if task_mapping is None:
            return []
        inputs_value = _find_field_value_in_mapping(task_mapping, "inputs")
        if inputs_value is None:
            return []
        sequence = _find_sequence_in_node(inputs_value)
        return sorted(_extract_named_io_from_sequence(sequence))
    except Exception as e:
        logger.debug("extract_task_inputs(%r) failed: %s", task_name, e)
        return []


def extract_task_outputs(tree: Tree, task_name: str) -> list[str]:
    """Extract named output identifiers for a specific task.

    Only *named* outputs (dict items like ``- binary: dist/app``) are
    returned.  Anonymous outputs (plain strings) are skipped.

    Args:
        tree:      Tree-sitter parse tree.
        task_name: Name of the task to inspect.

    Returns:
        Alphabetically sorted list of named output identifiers.
    """
    try:
        task_mapping = _find_task_mapping(tree, task_name)
        if task_mapping is None:
            return []
        outputs_value = _find_field_value_in_mapping(task_mapping, "outputs")
        if outputs_value is None:
            return []
        sequence = _find_sequence_in_node(outputs_value)
        return sorted(_extract_named_io_from_sequence(sequence))
    except Exception as e:
        logger.debug("extract_task_outputs(%r) failed: %s", task_name, e)
        return []


def extract_task_names(
    tree: Tree, base_path: str | None = None
) -> list[str]:
    """Extract task names from the document, including from imported files.

    Local task names are read from the ``tasks:`` section.  If
    ``base_path`` is provided, imported files are resolved relative to it
    and their task names are included with the ``namespace.`` prefix.

    Args:
        tree:      Tree-sitter parse tree.
        base_path: Directory of the current file for resolving imports.
                   Pass ``None`` to skip import resolution.

    Returns:
        Alphabetically sorted list of all available task names.
    """
    try:
        tasks_mapping = _find_section_mapping(tree.root_node, "tasks")
        task_names: list[str] = []

        if tasks_mapping is not None:
            for pair in _iter_mapping_pairs(tasks_mapping):
                name = _get_pair_key(pair)
                if name:
                    task_names.append(name)

        if base_path is not None:
            _extend_with_imported_task_names(tree, base_path, task_names)

        return sorted(task_names)
    except Exception as e:
        logger.debug("extract_task_names failed: %s", e)
        return []


def _extend_with_imported_task_names(
    tree: Tree, base_path: str, task_names: list[str]
) -> None:
    """Append namespaced task names from imported files into *task_names*.

    Reads each file listed in the ``imports:`` section and adds its task
    names with the namespace prefix (e.g. ``"utils.clean"`` for
    ``imports[].as: utils``).

    Limitation: only one level of imports is resolved.

    Args:
        tree:       Tree-sitter parse tree of the current file.
        base_path:  Directory of the current file.
        task_names: List to extend in-place.
    """
    try:
        imports_value = _find_section_value(tree.root_node, "imports")
        if imports_value is None:
            return

        imports_sequence = _find_sequence_in_node(imports_value)
        if imports_sequence is None:
            return

        for item in _iter_sequence_items(imports_sequence):
            item_mapping = _find_mapping_in_node(item)
            if item_mapping is None:
                continue

            import_file: str | None = None
            namespace: str | None = None

            for pair in _iter_mapping_pairs(item_mapping):
                key = _get_pair_key(pair)
                value_node = _get_pair_value_node(pair)
                if key == "file":
                    import_file = _get_scalar_value(value_node)
                elif key == "as":
                    namespace = _get_scalar_value(value_node)

            if not import_file or not namespace:
                continue

            try:
                import_path = Path(base_path) / import_file
                if not import_path.exists():
                    continue
                imported_text = import_path.read_text(encoding="utf-8")
                imported_tree = parse_document(imported_text)
                imported_tasks_mapping = _find_section_mapping(
                    imported_tree.root_node, "tasks"
                )
                if imported_tasks_mapping is None:
                    continue
                for pair in _iter_mapping_pairs(imported_tasks_mapping):
                    name = _get_pair_key(pair)
                    if name:
                        task_names.append(f"{namespace}.{name}")
            except OSError as e:
                logger.debug(
                    "Could not read import file %s: %s", import_file, e
                )
    except Exception as e:
        logger.debug("_extend_with_imported_task_names failed: %s", e)
