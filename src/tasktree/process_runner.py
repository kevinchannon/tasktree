"""Process execution abstraction layer.

This module provides an interface for running subprocesses, allowing for
better testability and dependency injection.
"""

import subprocess
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

__all__ = [
    "ProcessRunner",
    "PassthroughProcessRunner",
    "SilentProcessRunner",
    "TaskOutputTypes",
    "make_process_runner",
]


class TaskOutputTypes(Enum):
    """
    Enum defining task output control modes.
    @athena: TBD
    """

    ALL = "all"
    NONE = "none"


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


def make_process_runner(output_type: TaskOutputTypes) -> ProcessRunner:
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
    if output_type == TaskOutputTypes.ALL:
        return PassthroughProcessRunner()
    elif output_type == TaskOutputTypes.NONE:
        return SilentProcessRunner()
    else:
        raise ValueError(f"Invalid TaskOutputTypes: {output_type}")
