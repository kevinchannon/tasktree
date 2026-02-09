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
from pathlib import Path


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
        with TempScript(cmd="echo hello", preamble="set -e", shell="bash") as script_path:
            # script_path is a Path object pointing to the temp script
            subprocess.run([str(script_path)], check=True)
        # Script is automatically cleaned up after the with block

    @athena: class
    """

    def __init__(self, cmd: str, preamble: str = "", shell: str = "bash"):
        """
        Initialize temp script manager.

        Args:
            cmd: Command string to execute (can be multi-line)
            preamble: Optional preamble to prepend to command
            shell: Shell to use for shebang (default: bash)

        @athena: method
        """
        self.cmd = cmd
        self.preamble = preamble
        self.shell = shell
        self.script_path: Path | None = None

    def __enter__(self) -> Path:
        """
        Create temp script and return path.

        Creates a temporary script file with platform-appropriate extension,
        writes shebang (Unix/macOS only), preamble, and command. Makes the
        script executable on Unix/macOS.

        Returns:
            Path object pointing to the temporary script file

        @athena: method
        """
        # Determine file extension based on platform
        is_windows = platform.system() == "Windows"
        script_ext = ".bat" if is_windows else ".sh"

        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=script_ext,
            delete=False,
        ) as script_file:
            script_path_str = script_file.name

            # On Unix/macOS, add shebang if not present in command
            if not is_windows and not self.cmd.startswith("#!"):
                # Use the configured shell in shebang
                shebang = f"#!/usr/bin/env {self.shell}\n"
                script_file.write(shebang)

            # Add preamble if provided
            if self.preamble:
                script_file.write(self.preamble)
                if not self.preamble.endswith("\n"):
                    script_file.write("\n")

            # Write command to file
            script_file.write(self.cmd)
            script_file.flush()

        # Store path for cleanup
        self.script_path = Path(script_path_str)

        # Make executable on Unix/macOS
        if not is_windows:
            os.chmod(
                self.script_path,
                os.stat(self.script_path).st_mode | stat.S_IEXEC
            )

        return self.script_path

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Clean up temp script file.

        Deletes the temporary script file. Ignores any errors during cleanup
        to ensure cleanup doesn't interfere with exception propagation.

        Args:
            exc_type: Exception type (if an exception occurred)
            exc_val: Exception value (if an exception occurred)
            exc_tb: Exception traceback (if an exception occurred)

        @athena: method
        """
        if self.script_path:
            try:
                os.unlink(self.script_path)
            except OSError:
                pass  # Ignore cleanup errors
