"""
Temporary script file management.

This module provides the TempScript context manager for creating, managing,
and cleaning up temporary shell script files. It ensures consistent behavior
between containerized and non-containerized execution paths.

@athena: module
"""

import os
import platform
import stat
import tempfile
import types
from pathlib import Path

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
    writes a shebang (Unix/macOS only), optional preamble, and the command
    to execute. On Unix/macOS, the script is made executable.

    Usage:
        with TempScript(logger=my_logger, cmd="echo hello", preamble="set -e", shell="bash") as script_path:
            # script_path is a Path object pointing to the temp script
            subprocess.run([str(script_path)], check=True)
        # Script is automatically cleaned up after the with block

    @athena: class
    """

    def __init__(
        self,
        logger: Logger,
        cmd: str,
        preamble: str = "",
        shell: str = "bash",
        script_extension: str | None = None,
        use_shebang: bool | None = None,
    ):
        """
        Initialize temp script manager.

        Args:
            logger: Logger for debug/trace logging
            cmd: Command string to execute (can be multi-line)
            preamble: Optional preamble to prepend to command
            shell: Shell to use for shebang (default: bash)
            script_extension: Optional override for script file extension (e.g., ".sh", ".bat", ".ps1").
                            If None, determined from platform.
            use_shebang: Optional override for whether to add shebang.
                        If None, determined from platform (True on Unix/macOS, False on Windows).

        @athena: method
        """
        self.cmd = cmd
        self.preamble = preamble
        self.shell = shell
        self.logger = logger
        self.script_path: Path | None = None
        self.script_extension = script_extension
        self.use_shebang = use_shebang

    def __enter__(self) -> Path:
        """
        Create temp script and return path.

        Creates a temporary script file with platform-appropriate extension,
        writes shebang (Unix/macOS only by default), preamble, and command.
        Makes the script executable on Unix/macOS.

        Note: There is a small race condition window between file creation
        (with delete=False) and chmod on Unix/macOS. A malicious process could
        potentially access the file before permissions are set. This is accepted
        as the temp directory should have appropriate permissions and the window
        is very small.

        Returns:
            Path object pointing to the temporary script file

        @athena: method
        """
        # Determine file extension (use override if provided, otherwise platform default)
        if self.script_extension is not None:
            script_ext = self.script_extension
        else:
            script_ext = ".bat" if _IS_WINDOWS else ".sh"

        # Determine whether to use shebang (use override if provided, otherwise platform default)
        if self.use_shebang is not None:
            should_use_shebang = self.use_shebang
        else:
            should_use_shebang = not _IS_WINDOWS

        self.logger.debug(f"Creating temp script with extension {script_ext}")

        # Create temporary script file with explicit UTF-8 encoding
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=script_ext,
            delete=False,
            encoding="utf-8",
        ) as script_file:
            script_path_str = script_file.name

            # Add shebang if enabled and not already present in command
            if should_use_shebang:
                if not self.cmd.startswith("#!"):
                    # Use the configured shell in shebang
                    shebang = f"#!/usr/bin/env {self.shell}\n"
                    script_file.write(shebang)
                    self.logger.debug(f"Added shebang: {shebang.strip()}")

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

        # Make executable on Unix/macOS (only for non-Windows scripts)
        if not _IS_WINDOWS and script_ext == ".sh":
            os.chmod(
                self.script_path,
                os.stat(self.script_path).st_mode | stat.S_IEXEC
            )
            self.logger.debug("Set executable permissions on script")

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

        @athena: method
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
