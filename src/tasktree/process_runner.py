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


def make_process_runner(task_output: str) -> ProcessRunner:
    """
    Factory function to create a ProcessRunner based on task_output mode.

    Args:
        task_output: Output control mode ("all", "none", etc.)

    Returns:
        ProcessRunner instance configured for the specified output mode
    """
    suppress_output = task_output.lower() == "none"
    return StreamingProcessRunner(
        show_stdout=not suppress_output,
        show_stderr=not suppress_output,
    )
