"""Interpreter value type for tasktree.

An interpreter describes, literally, how to run a task's temporary script:
- ``cmd``: the command used to invoke the interpreter, tokenised with
  ``shlex`` and used verbatim (no lookups, no defaults, no fallbacks).
- ``ext``: the temp-script file extension. Empty means the script has no
  extension. When non-empty it must start with a dot.
- ``preamble``: text prepended to every task body run by this interpreter.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass


class InterpreterError(Exception):
    """Raised when an interpreter definition is invalid or unresolved."""

    pass


@dataclass(frozen=True)
class Interpreter:
    """A literal description of how to invoke a temp script."""

    cmd: str
    ext: str = ""
    preamble: str = ""

    def __post_init__(self):
        if not self.cmd:
            raise InterpreterError("Interpreter 'cmd' must be a non-empty string")
        if self.ext and not self.ext.startswith("."):
            raise InterpreterError(
                f"Interpreter 'ext' must start with a dot (got {self.ext!r})"
            )

    @property
    def invocation(self) -> list[str]:
        """The interpreter command tokens, used verbatim before the script path."""
        return shlex.split(self.cmd)
