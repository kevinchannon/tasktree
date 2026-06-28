"""Interpreter strategy type for tasktree."""

from __future__ import annotations

import platform
from collections.abc import Sequence
from dataclasses import dataclass, field


class UnknownInterpreterError(Exception):
    """Raised when an unknown interpreter name is requested."""

    pass


def _derive_script_extension(name: str) -> str:
    """Derive a canonical script extension from an interpreter/shell name.

    PowerShell needs ``.ps1`` and cmd.exe needs ``.bat`` because those
    interpreters dispatch on file extension; everything else uses ``.sh``.
    Used for custom shell invocations not present in INTERPRETER_LOOKUP.
    """
    lowered = name.lower()
    if "powershell" in lowered or "pwsh" in lowered:
        return ".ps1"
    if "cmd" in lowered:
        return ".bat"
    return ".sh"


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

    @staticmethod
    def from_shell_cmd(cmd: Sequence[str]) -> "Interpreter":
        """Derive an Interpreter from a shell invocation list.

        Backward-compat bridge for runners that configure ``shell.cmd`` but no
        explicit ``interpreter``. The invocation list is preserved verbatim
        (so custom flags survive) and the script extension is taken from the
        known interpreter, or derived from the executable name otherwise.
        """
        if not cmd:
            return Interpreter.host_default()
        name = cmd[0]
        known = INTERPRETER_LOOKUP.get(name)
        extension = (
            known.script_extension if known else _derive_script_extension(name)
        )
        return Interpreter(
            name=name, invocation_cmd=tuple(cmd), script_extension=extension
        )

    def host_script_extension(self) -> str:
        """Return the temp-script extension to use on the host execution path.

        On Unix the interpreter is invoked explicitly (``bash /tmp/script``),
        so no extension is needed. On Windows, cmd.exe and PowerShell dispatch
        scripts by extension, so ``.bat``/``.ps1`` are load-bearing; other
        interpreters still need none.
        """
        if platform.system() != "Windows":
            return ""
        if self.script_extension in (".bat", ".ps1"):
            return self.script_extension
        return ""


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
