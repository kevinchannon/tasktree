"""
Jinja2-based template rendering for task definitions.

This module renders a task definition field (a string template) against a
single context object that holds all variable namespaces (var, arg, env, tt,
dep, self). It replaces the hand-rolled regex substitution in substitution.py.

Jinja2 errors are intercepted and translated into actionable, Tasktree-flavoured
messages. Users should never see a raw Jinja2 traceback.
"""

import re
from typing import Any

from jinja2 import (
    Environment,
    StrictUndefined,
    TemplateError,
    TemplateSyntaxError,
    UndefinedError,
)


def _finalize(value: Any) -> Any:
    """
    Coerce rendered values to Tasktree's string conventions.

    Booleans render as lowercase ``true``/``false`` to match YAML/shell
    conventions (Jinja2's default would be ``True``/``False``).
    """
    if isinstance(value, bool):
        return str(value).lower()
    return value


def _build_environment() -> Environment:
    """Create the Jinja2 environment used for all task rendering."""
    return Environment(
        undefined=StrictUndefined,
        finalize=_finalize,
        autoescape=False,
        keep_trailing_newline=True,
    )


_ENVIRONMENT = _build_environment()

# Jinja2 reserves ``self`` (it refers to the template's own block namespace), so
# the recipe-facing ``{{ self.inputs.x }}`` syntax must be rewritten to a
# non-reserved name before rendering. This rewrite is confined to this module;
# the rest of Tasktree (and the config object) keeps the logical name ``self``.
_RESERVED_ALIAS = "this"
_TEMPLATE_BLOCK = re.compile(r"\{\{.*?}}", re.DOTALL)
_SELF_NAMESPACE = re.compile(r"\bself\.")

# Dependency task names may be namespaced with dots (e.g. ``build.compile``),
# which Jinja2 cannot dot-access. Rewrite ``dep.<name>.outputs.<output>`` to
# subscript form ``dep["<name>"].outputs.<output>`` so the full dotted name is
# treated as a single key. This also covers simple (un-namespaced) names.
_DEP_OUTPUT = re.compile(
    r"\bdep\.([a-zA-Z_][a-zA-Z0-9_.-]*)\.outputs\.([a-zA-Z_][a-zA-Z0-9_]*)"
)


def _translate_block(block: str) -> str:
    """Apply all reserved-syntax rewrites within a single ``{{ ... }}`` block."""
    block = _SELF_NAMESPACE.sub(f"{_RESERVED_ALIAS}.", block)
    block = _DEP_OUTPUT.sub(r'dep["\1"].outputs.\2', block)
    return block


def _translate_reserved(text: str) -> str:
    """
    Rewrite recipe-facing syntax into valid Jinja2.

    Only ``{{ ... }}`` expression blocks are rewritten, so literal text elsewhere
    in a command is left untouched.
    """
    return _TEMPLATE_BLOCK.sub(lambda m: _translate_block(m.group(0)), text)


def _alias_reserved(context: dict[str, Any]) -> dict[str, Any]:
    """Expose the ``self`` namespace under the non-reserved alias."""
    if "self" not in context:
        return context
    return {**context, _RESERVED_ALIAS: context["self"]}


def render(text: str, context: dict[str, Any], task_name: str | None = None) -> str:
    """
    Render a template string against a context of variable namespaces.

    Args:
    text: Template string (may contain {{ ... }} placeholders)
    context: Mapping of namespace name (var, arg, env, tt, dep, self) to values
    task_name: Optional task name, used to make error messages actionable

    Returns:
    The rendered string

    Raises:
    ValueError: If the template references an undefined value or is malformed.
    The message is Tasktree-flavoured and never exposes Jinja2 internals.
    """
    if not isinstance(text, str):
        return text

    where = f" in task '{task_name}'" if task_name else ""

    text = _translate_reserved(text)
    context = _alias_reserved(context)

    try:
        template = _ENVIRONMENT.from_string(text)
        return template.render(context)
    except UndefinedError as e:
        raise ValueError(
            f"Undefined variable{where}: {_clean_message(str(e))}"
        ) from e
    except TemplateSyntaxError as e:
        raise ValueError(
            f"Malformed template{where} (line {e.lineno}): {_clean_message(e.message or str(e))}"
        ) from e
    except TemplateError as e:
        raise ValueError(
            f"Template error{where}: {_clean_message(str(e))}"
        ) from e


def _clean_message(message: str) -> str:
    """Strip Jinja2 implementation details from an error message."""
    # StrictUndefined messages look like: "'foo' is undefined" or
    # "'dict object' has no attribute 'bar'". Keep them, they are readable.
    return message.replace("jinja2.exceptions.", "").strip()
