"""Interpreter strategy type for tasktree."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field


class UnknownInterpreterError(Exception):
    """Raised when an unknown interpreter name is requested."""

    pass


@dataclass(frozen=True)
class Interpreter:
    """Strategy object describing how to invoke a temp script."""

    name: str
    invocation_cmd: tuple[str, ...] = field(default_factory=tuple)
    script_extension: str = ""

    @staticmethod
    def from_name(name: str) -> "Interpreter":
        """Create an Interpreter from a well-known name."""
        if name not in INTERPRETER_LOOKUP:
            raise UnknownInterpreterError(
                f"Unknown interpreter '{name}'. "
                f"Known interpreters: {sorted(INTERPRETER_LOOKUP)}"
            )
        return INTERPRETER_LOOKUP[name]

    @staticmethod
    def host_default() -> "Interpreter":
        """Return the default interpreter for the host runner."""
        if platform.system() == "Windows":
            return INTERPRETER_LOOKUP["cmd.exe"]
        return INTERPRETER_LOOKUP["bash"]

    @staticmethod
    def container_default() -> "Interpreter":
        """Return the default interpreter for container runners."""
        return INTERPRETER_LOOKUP["sh"]


# Canonical lookup table mapping interpreter names to Interpreter instances.
# Script extensions: cosmetic on Unix (.sh), load-bearing on Windows (.bat/.ps1).
INTERPRETER_LOOKUP: dict[str, Interpreter] = {
    "bash": Interpreter(name="bash", invocation_cmd=("bash",), script_extension=".sh"),
    "sh": Interpreter(name="sh", invocation_cmd=("sh",), script_extension=".sh"),
    "zsh": Interpreter(name="zsh", invocation_cmd=("zsh",), script_extension=".sh"),
    "fish": Interpreter(name="fish", invocation_cmd=("fish",), script_extension=".fish"),
    "cmd.exe": Interpreter(
        name="cmd.exe", invocation_cmd=("cmd.exe", "/c"), script_extension=".bat"
    ),
    "powershell": Interpreter(
        name="powershell",
        invocation_cmd=("powershell", "-ExecutionPolicy", "Bypass", "-File"),
        script_extension=".ps1",
    ),
    "pwsh": Interpreter(
        name="pwsh",
        invocation_cmd=("pwsh", "-ExecutionPolicy", "Bypass", "-File"),
        script_extension=".ps1",
    ),
    "python": Interpreter(
        name="python", invocation_cmd=("python",), script_extension=".py"
    ),
    "python3": Interpreter(
        name="python3", invocation_cmd=("python3",), script_extension=".py"
    ),
}
