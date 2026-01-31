"""Test helpers for ProcessRunner mocking."""

from pathlib import Path
from typing import Callable


class MockProcessRunner:
    """
    Mock ProcessRunner for testing.

    Records all run() calls and returns configurable exit codes.
    Provides access to the most recent command for test assertions.
    """

    # Class-level shared state to allow capturing commands across instances
    _shared_calls = []
    _last_docker_command = None

    def __init__(self, exit_code: int = 0):
        """
        Initialize mock ProcessRunner.

        Args:
            exit_code: Exit code to return from run() calls
        """
        self.exit_code = exit_code
        self.calls = []  # Instance-specific calls

    def run(
        self,
        cmd: list[str],
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> int:
        """
        Mock run method that records calls.

        Args:
            cmd: Command and arguments
            cwd: Working directory
            env: Environment variables

        Returns:
            Configured exit code
        """
        self.calls.append((cmd, cwd, env))
        MockProcessRunner._shared_calls.append((cmd, cwd, env))

        # Capture docker run commands
        if isinstance(cmd, list) and len(cmd) > 0 and "docker" in cmd[0]:
            if "run" in cmd:
                MockProcessRunner._last_docker_command = cmd

        return self.exit_code

    @classmethod
    def get_last_docker_command(cls):
        """Get the last docker run command that was executed."""
        return cls._last_docker_command

    @classmethod
    def reset(cls):
        """Reset shared state (call in test setUp)."""
        cls._shared_calls = []
        cls._last_docker_command = None


def make_mock_process_runner_factory(
    exit_code: int = 0,
) -> Callable[[str], MockProcessRunner]:
    """
    Create a factory function that returns MockProcessRunner instances.

    Args:
        exit_code: Exit code for the mock runners to return

    Returns:
        Factory function compatible with Executor's process_runner_factory parameter
    """
    def factory(task_output: str) -> MockProcessRunner:
        return MockProcessRunner(exit_code=exit_code)

    return factory
