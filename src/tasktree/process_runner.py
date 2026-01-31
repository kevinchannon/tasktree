"""Process execution abstraction layer.

This module provides an interface for running subprocesses, allowing for
better testability and dependency injection.
"""

import subprocess
from abc import ABC, abstractmethod
from typing import Any

__all__ = ['ProcessRunner', 'PassthroughProcessRunner']


class ProcessRunner(ABC):
    """Abstract interface for running subprocess commands."""

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """Run a subprocess command.

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
        """
        ...


class PassthroughProcessRunner(ProcessRunner):
    """Process runner that directly delegates to subprocess.run."""

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """Run a subprocess command via subprocess.run.

        Args:
            *args: Positional arguments passed to subprocess.run
            **kwargs: Keyword arguments passed to subprocess.run

        Returns:
            subprocess.CompletedProcess: The completed process result

        Raises:
            subprocess.CalledProcessError: If check=True and process exits non-zero
            subprocess.TimeoutExpired: If timeout is exceeded
        """
        return subprocess.run(*args, **kwargs)
