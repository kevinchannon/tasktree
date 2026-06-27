"""
Interpreter strategy type for tasktree.

An Interpreter encapsulates how a temp script is invoked (the command prefix)
and what file extension the temp script should carry. It is independent of the
runner (where execution happens).
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field


class UnknownInterpreterError(Exception):
    """Raised when an unknown interpreter name is requested."""

    pass


@dataclass
class Interpreter:
    """
    Strategy object describing how to invoke a temp script.

    Holds the script-invocation form (command prefix applied before the script
    path) and the temp-script file extension. Does not hold shebang or inline
    invocation forms — tasktree always writes a temp script and passes it to
    the named interpreter.
    """

    name: str
    invocation_cmd: list[str] = field(default_factory=list)
    script_extension: str = ""

    @classmethod
    def from_name(cls, name: str) -> "Interpreter":
        """
        Create an Interpreter from a well-known name.

        Args:
            name: Interpreter name, e.g. "bash", "sh", "powershell", "python3".

        Raises:
            UnknownInterpreterError: If the name is not in INTERPRETER_LOOKUP.
        """
        if name not in INTERPRETER_LOOKUP:
            raise UnknownInterpreterError(
                f"Unknown interpreter '{name}'. "
                f"Known interpreters: {sorted(INTERPRETER_LOOKUP)}"
            )
        return INTERPRETER_LOOKUP[name]

    @classmethod
    def host_default(cls) -> "Interpreter":
        """
        Return the default interpreter for the host (process) runner.

        Returns bash on Unix/macOS, cmd.exe on Windows.
        """
        if platform.system() == "Windows":
            return INTERPRETER_LOOKUP["cmd.exe"]
        return INTERPRETER_LOOKUP["bash"]

    @classmethod
    def container_default(cls) -> "Interpreter":
        """
        Return the default interpreter for container runners (docker/podman).

        Always returns sh — the lowest common denominator available in
        minimal container images.
        """
        return INTERPRETER_LOOKUP["sh"]


# Canonical lookup table mapping interpreter names to Interpreter instances.
# Script extensions: cosmetic on Unix (.sh), load-bearing on Windows (.bat/.ps1).
INTERPRETER_LOOKUP: dict[str, Interpreter] = {
    "bash": Interpreter(name="bash", invocation_cmd=["bash"], script_extension=".sh"),
    "sh": Interpreter(name="sh", invocation_cmd=["sh"], script_extension=".sh"),
    "zsh": Interpreter(name="zsh", invocation_cmd=["zsh"], script_extension=".sh"),
    "fish": Interpreter(name="fish", invocation_cmd=["fish"], script_extension=".sh"),
    "cmd.exe": Interpreter(
        name="cmd.exe", invocation_cmd=["cmd.exe", "/c"], script_extension=".bat"
    ),
    "powershell": Interpreter(
        name="powershell",
        invocation_cmd=["powershell", "-ExecutionPolicy", "Bypass", "-File"],
        script_extension=".ps1",
    ),
    "pwsh": Interpreter(
        name="pwsh",
        invocation_cmd=["pwsh", "-ExecutionPolicy", "Bypass", "-File"],
        script_extension=".ps1",
    ),
    "python": Interpreter(
        name="python", invocation_cmd=["python"], script_extension=".py"
    ),
    "python3": Interpreter(
        name="python3", invocation_cmd=["python3"], script_extension=".py"
    ),
}
