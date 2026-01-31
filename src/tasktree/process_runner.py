"""Process runner abstraction for subprocess execution.

Provides a mockable interface for running subprocesses with configurable
output handling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from threading import Thread
from typing import Protocol


class ProcessRunner(Protocol):
    """
    Interface for running subprocesses with configurable output.

    This abstraction allows for easy mocking in tests and encapsulates
    subprocess execution logic.
    """

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        """
        Run a subprocess command.

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory for the subprocess
            env: Environment variables (None uses os.environ)

        Returns:
            Exit code of the subprocess

        Raises:
            Does not raise - caller should check exit code
        """
        ...


class StreamingProcessRunner:
    """
    ProcessRunner that streams output in real-time or suppresses it.

    Uses subprocess.Popen with threading to stream stdout/stderr as they
    arrive, working correctly in both production and CliRunner test contexts.
    """

    def __init__(self, show_stdout: bool = True, show_stderr: bool = True):
        """
        Initialize the streaming process runner.

        Args:
            show_stdout: Whether to display subprocess stdout
            show_stderr: Whether to display subprocess stderr
        """
        self.show_stdout = show_stdout
        self.show_stderr = show_stderr

    @staticmethod
    def _stream_output(pipe, target):
        """
        Stream lines from pipe to target as they arrive.

        Args:
            pipe: Readable stream to read from
            target: Writable stream to write to (sys.stdout or sys.stderr)
        """
        if pipe:
            for line in pipe:
                target.write(line)
                target.flush()

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        """
        Run subprocess with streaming output.

        Streams stdout/stderr to sys.stdout/sys.stderr in real-time using threads.
        Works correctly in both production and CliRunner test contexts.

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory
            env: Environment variables (None uses inherited environment)

        Returns:
            Exit code of the subprocess

        Raises:
            Does not raise - caller should check exit code
        """
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE if self.show_stdout else subprocess.DEVNULL,
            stderr=subprocess.PIPE if self.show_stderr else subprocess.DEVNULL,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Use threads to avoid deadlock when both stdout and stderr have data
        threads = []

        if self.show_stdout and process.stdout:
            t = Thread(
                target=StreamingProcessRunner._stream_output,
                args=(process.stdout, sys.stdout),
            )
            t.start()
            threads.append(t)

        if self.show_stderr and process.stderr:
            t = Thread(
                target=StreamingProcessRunner._stream_output,
                args=(process.stderr, sys.stderr),
            )
            t.start()
            threads.append(t)

        # Wait for all output to be consumed
        for t in threads:
            t.join()

        # Wait for process to complete
        return process.wait()


class PassthroughProcessRunner:
    """
    ProcessRunner that passes through all output using subprocess.run.

    Uses capture_output=False to let subprocess output flow directly to
    the terminal. This is the legacy behavior before task output control.
    """

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        """
        Run subprocess with passthrough output.

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory
            env: Environment variables (None uses inherited environment)

        Returns:
            Exit code of the subprocess

        Raises:
            subprocess.CalledProcessError: If check=True and process fails
        """
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            stdout=None,
            stderr=None,
            check=False,
        )
        return result.returncode


class SilentProcessRunner:
    """
    ProcessRunner that suppresses all output using subprocess.run.

    Uses capture_output=True and discards the output. More efficient than
    streaming when output is not needed.
    """

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        """
        Run subprocess with suppressed output.

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory
            env: Environment variables (None uses inherited environment)

        Returns:
            Exit code of the subprocess

        Raises:
            subprocess.CalledProcessError: If check=True and process fails
        """
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            check=False,
        )
        return result.returncode


class CapturingProcessRunner:
    """
    ProcessRunner that captures output for inspection.

    Captures stdout and stderr, making them available via stdout/stderr attributes.
    Used for utility commands where we need to inspect the output.
    """

    def __init__(self):
        """Initialize the capturing process runner."""
        self.stdout = ""
        self.stderr = ""
        self.returncode = 0

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        """
        Run subprocess and capture output.

        Args:
            cmd: Command and arguments to execute
            cwd: Working directory
            env: Environment variables (None uses inherited environment)

        Returns:
            Exit code of the subprocess
        """
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.stdout = result.stdout
        self.stderr = result.stderr
        self.returncode = result.returncode
        return result.returncode


def make_process_runner(task_output: str) -> ProcessRunner:
    """
    Factory function to create a ProcessRunner based on task_output mode.

    Args:
        task_output: Output control mode ("all", "none", etc.)

    Returns:
        ProcessRunner instance configured for the specified output mode
    """
    if task_output.lower() == "none":
        return SilentProcessRunner()
    else:
        return PassthroughProcessRunner()
