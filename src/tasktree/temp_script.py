"""
Temporary script file management.

This module provides the TempScript context manager for creating, managing,
and cleaning up temporary shell script files. It ensures consistent behavior
between containerized and non-containerized execution paths.

"""

import os
import platform
import tempfile
import types
from pathlib import Path

from tasktree.interpreter import Interpreter
from tasktree.logging import Logger

# Module-level constant for platform detection to avoid repeated system calls
_IS_WINDOWS = platform.system() == "Windows"


class TempScript:
    """
    Context manager for temporary script files.

    Handles creation, execution preparation, and cleanup of temporary
    shell scripts. Ensures consistent behavior between containerized
    and non-containerized execution.

    The context manager creates a temporary script file with the appropriate
    platform-specific extension (.sh for Unix/macOS, .bat for Windows),
    writes an optional preamble, and the command to execute. The interpreter
    is always passed explicitly when invoking the script, so no shebang is
    written and no executable bit is set.

    Usage:
        with TempScript(logger=my_logger, cmd="echo hello", preamble="set -e", interpreter=Interpreter(cmd="bash")) as script_path:
            # script_path is a Path object pointing to the temp script
            subprocess.run(["bash", str(script_path)], check=True)
        # Script is automatically cleaned up after the with block

    """

    def __init__(
        self,
        logger: Logger,
        cmd: str,
        preamble: str = "",
        script_extension: str | None = None,
        interpreter: Interpreter | None = None,
    ):
        """
        Initialize temp script manager.

        Args:
            logger: Logger for debug/trace logging
            cmd: Command string to execute (can be multi-line)
            preamble: Optional preamble to prepend to command
            script_extension: Optional override for script file extension (e.g., ".sh", ".bat", ".ps1").
                            If None, derived from ``interpreter`` when provided, otherwise the platform.
            interpreter: Optional Interpreter describing how the script is run.
                        When provided, supplies the default script extension.

        """
        self.cmd = cmd
        self.preamble = preamble
        self.logger = logger
        self.script_path: Path | None = None
        self.script_extension = script_extension
        self.interpreter = interpreter

    def __enter__(self) -> Path:
        """
        Create temp script and return path.

        Creates a temporary script file with platform-appropriate extension,
        writes optional preamble and command.

        Returns:
            Path object pointing to the temporary script file

        """
        # Determine file extension: explicit override first, then the
        # interpreter's extension, then the platform default.
        if self.script_extension is not None:
            script_ext = self.script_extension
        elif self.interpreter is not None:
            script_ext = self.interpreter.ext
        else:
            script_ext = ".bat" if _IS_WINDOWS else ".sh"

        self.logger.debug(f"Creating temp script with extension {script_ext}")

        # Create temporary script file with explicit UTF-8 encoding
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=script_ext,
            delete=False,
            encoding="utf-8",
        ) as script_file:
            script_path_str = script_file.name

            # Add preamble if provided
            if self.preamble:
                script_file.write(self.preamble)
                if not self.preamble.endswith("\n"):
                    script_file.write("\n")
                self.logger.debug("Added preamble to script")

            # Write command to file
            script_file.write(self.cmd)
            script_file.flush()

        # Store path for cleanup
        self.script_path = Path(script_path_str)

        self.logger.debug(f"Created temp script at: {self.script_path}")

        return self.script_path

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """
        Clean up temp script file.

        Deletes the temporary script file. OSError exceptions during cleanup
        are caught and logged (if logger available) but not raised. This ensures
        cleanup failures don't interfere with exception propagation from the
        context manager body. File leaks are acceptable in edge cases where
        cleanup fails, as the OS will eventually clean up temp files.

        Args:
            exc_type: Exception type (if an exception occurred)
            exc_val: Exception value (if an exception occurred)
            exc_tb: Exception traceback (if an exception occurred)

        """
        if self.script_path:
            try:
                os.unlink(self.script_path)
                self.logger.debug(f"Cleaned up temp script: {self.script_path}")
            except OSError as e:
                # Log cleanup failure but don't raise to avoid masking exceptions
                # from the context manager body
                self.logger.warn(
                    f"Failed to clean up temp script {self.script_path}: {e}"
                )
