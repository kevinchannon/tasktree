"""Process execution abstraction layer.

This module provides an interface for running subprocesses, allowing for
better testability and dependency injection.
"""

import subprocess
import sys
from abc import ABC, abstractmethod
from enum import Enum
from subprocess import Popen
from threading import Thread
from typing import Any

__all__ = [
    "ProcessRunner",
    "PassthroughProcessRunner",
    "SilentProcessRunner",
    "StdoutOnlyProcessRunner",
    "StderrOnlyProcessRunner",
    "TaskOutputTypes",
    "make_process_runner",
    "stream_output"
]

from tasktree.logging import Logger


class TaskOutputTypes(Enum):
    """
    Enum defining task output control modes.
    @athena: TBD
    """

    ALL = "all"
    NONE = "none"
    OUT = "out"
    ERR = "err"


class ProcessRunner(ABC):
    """
    Abstract interface for running subprocess commands.
    @athena: 78720f594104
    """

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """
        Run a subprocess command.

        This method signature matches subprocess.run() to allow for direct
        substitution in existing code.

        Args:
        *args: Positional arguments passed to subprocess.run
        **kwargs: Keyword arguments passed to subprocess.run

        Returns:
        subprocess.CompletedProcess: The completed process result

        Raises:
        subprocess.CalledProcessError: If check=True and process exits non-zero
        subprocess.TimeoutExpired: If timeout is exceeded
        @athena: c056d217be2e
        """
        ...


class PassthroughProcessRunner(ProcessRunner):
    """
    Process runner that directly delegates to subprocess.run.
    @athena: 470e2ca46355
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """
        Run a subprocess command via subprocess.run.

        Args:
        *args: Positional arguments passed to subprocess.run
        **kwargs: Keyword arguments passed to subprocess.run

        Returns:
        subprocess.CompletedProcess: The completed process result

        Raises:
        subprocess.CalledProcessError: If check=True and process exits non-zero
        subprocess.TimeoutExpired: If timeout is exceeded
        @athena: 9f6363a621f2
        """
        return subprocess.run(*args, **kwargs)


class SilentProcessRunner(ProcessRunner):
    """
    Process runner that suppresses all subprocess output by redirecting to DEVNULL.
    @athena: TBD
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """
        Run a subprocess command with stdout and stderr suppressed.

        This implementation forces stdout=DEVNULL and stderr=DEVNULL to discard
        all subprocess output, regardless of what the caller requests.

        Args:
        *args: Positional arguments passed to subprocess.run
        **kwargs: Keyword arguments passed to subprocess.run

        Returns:
        subprocess.CompletedProcess: The completed process result

        Raises:
        subprocess.CalledProcessError: If check=True and process exits non-zero
        subprocess.TimeoutExpired: If timeout is exceeded
        @athena: TBD
        """
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
        return subprocess.run(*args, **kwargs)


def stream_output(pipe: Any, target: Any) -> None:
    """
    Stream output from a pipe to a target stream.

    Handles exceptions gracefully to avoid silent thread failures.
    If the pipe is closed or an error occurs during reading/writing,
    the function returns without raising an exception.

    Args:
        pipe: Input pipe to read from
        target: Output stream to write to
    @athena: TBD
    """
    if pipe:
        try:
            for line in pipe:
                target.write(line)
                target.flush()
        except (OSError, ValueError):
            # Pipe closed or other I/O error - this is expected when
            # process is killed or stdout is closed
            pass


def _start_thread_and_wait_to_complete(process: Popen[str], stream: Any, thread: Thread, process_allowed_runtime: float | None, logger: Logger) -> int:
    join_timeout_secs = 1.0

    thread.start()

    try:
        process_return_code = process.wait(timeout=process_allowed_runtime)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        if stream:
            stream.close()
        thread.join(timeout=join_timeout_secs)
        raise
    finally:
        if stream:
            stream.close()

    thread.join(timeout=join_timeout_secs)
    if thread.is_alive():
        logger.warn(f"Stream thread did not complete within timeout of {join_timeout_secs} seconds")

    return process_return_code


def _check_result_if_necessary(raise_on_failure: bool, proc_ret_code: int, *args, **kwargs) -> subprocess.CompletedProcess[Any]:
    if raise_on_failure and proc_ret_code != 0:
        raise subprocess.CalledProcessError(
            proc_ret_code, args[0] if args else kwargs.get("args", [])
        )

    # Return a CompletedProcess object for interface compatibility
    return subprocess.CompletedProcess(
        args=args[0] if args else kwargs.get("args", []),
        returncode=proc_ret_code,
        stdout=None,
        stderr=None,  # We streamed it, so don't capture it
    )


class StdoutOnlyProcessRunner(ProcessRunner):
    """
    Process runner that streams stdout while suppressing stderr.

    This implementation uses threading to asynchronously stream stdout from the
    subprocess while discarding stderr output.
    @athena: TBD
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """
        Run a subprocess command with stdout streamed and stderr suppressed.

        This implementation uses subprocess.Popen with threading to stream stdout
        in real-time while discarding stderr. The interface remains synchronous
        from the caller's perspective.

        Buffering strategy: Uses line buffering (bufsize=1) to ensure output
        appears promptly while maintaining reasonable performance.

        Args:
            *args: Positional arguments passed to subprocess.Popen
            **kwargs: Keyword arguments passed to subprocess.Popen

        Returns:
            subprocess.CompletedProcess: The completed process result

        Raises:
            subprocess.CalledProcessError: If check=True and process exits non-zero
            subprocess.TimeoutExpired: If timeout is exceeded
        @athena: TBD
        """
        # Extract parameters that need special handling
        check = kwargs.pop("check", False)
        timeout = kwargs.pop("timeout", None)
        # Remove capture_output if present - not supported by Popen
        kwargs.pop("capture_output", None)

        # Force stdout/stderr handling
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.DEVNULL
        kwargs["text"] = True
        kwargs["bufsize"] = 1

        # Start the process
        process = subprocess.Popen(*args, **kwargs)

        # Start thread to stream stdout with a descriptive name for debugging
        thread = Thread(
            target=stream_output,
            args=(process.stdout, sys.stdout),
            name="stdout-streamer",
        )

        process_return_code = _start_thread_and_wait_to_complete(process, process.stdout, thread, timeout, self._logger)
        return _check_result_if_necessary(check, process_return_code, *args, **kwargs)


class StderrOnlyProcessRunner(ProcessRunner):
    """
    Process runner that streams stderr while suppressing stdout.

    This implementation uses threading to asynchronously stream stderr from the
    subprocess while discarding stdout output.
    @athena: TBD
    """

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """
        Run a subprocess command with stderr streamed and stdout suppressed.

        This implementation uses subprocess.Popen with threading to stream stderr
        in real-time while discarding stdout. The interface remains synchronous
        from the caller's perspective.

        Buffering strategy: Uses line buffering (bufsize=1) to ensure output
        appears promptly while maintaining reasonable performance.

        Args:
            *args: Positional arguments passed to subprocess.Popen
            **kwargs: Keyword arguments passed to subprocess.Popen

        Returns:
            subprocess.CompletedProcess: The completed process result

        Raises:
            subprocess.CalledProcessError: If check=True and process exits non-zero
            subprocess.TimeoutExpired: If timeout is exceeded
        @athena: TBD
        """
        # Extract parameters that need special handling
        check = kwargs.pop("check", False)
        timeout = kwargs.pop("timeout", None)
        # Remove capture_output if present - not supported by Popen
        kwargs.pop("capture_output", None)

        # Force stdout/stderr handling
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
        kwargs["bufsize"] = 1

        # Start the process
        process = subprocess.Popen(*args, **kwargs)

        # Start thread to stream stderr with a descriptive name for debugging
        thread = Thread(
            target=stream_output,
            args=(process.stderr, sys.stderr),
            name="stderr-streamer",
        )

        process_return_code = _start_thread_and_wait_to_complete(process, process.stderr, thread, timeout, self._logger)
        return _check_result_if_necessary(check, process_return_code, *args, **kwargs)


def make_process_runner(output_type: TaskOutputTypes, logger: Logger) -> ProcessRunner:
    """
    Factory function for creating ProcessRunner instances.

    Args:
    output_type: The type of output control to use

    Returns:
    ProcessRunner: A new ProcessRunner instance

    Raises:
    ValueError: If an invalid TaskOutputTypes value is provided
    @athena: ba1d2e048716
    """
    match output_type:
        case TaskOutputTypes.ALL:
            return PassthroughProcessRunner(logger)
        case TaskOutputTypes.NONE:
            return SilentProcessRunner(logger)
        case TaskOutputTypes.OUT:
            return StdoutOnlyProcessRunner(logger)
        case TaskOutputTypes.ERR:
            return StderrOnlyProcessRunner(logger)
        case _:
            raise ValueError(f"Invalid TaskOutputTypes: {output_type}")
