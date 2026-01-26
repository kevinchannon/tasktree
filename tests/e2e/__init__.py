"""
E2E test utilities for Docker tests.
@athena: 2a3158f02816
"""

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional


def is_docker_available() -> bool:
    """Check if Docker is installed and running.

    Returns:
        True if docker command exists and daemon is running
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


def run_tasktree_cli(
    args: list[str],
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Execute tasktree CLI via subprocess.

    Uses sys.executable to run code under test (not system-installed tt).

    Args:
        args: CLI arguments (e.g., ["build", "--force"])
        cwd: Working directory for execution
        env: Additional environment variables

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    cmd = [sys.executable, "-m", "tasktree.cli"] + args

    # Merge environment variables
    exec_env = {**os.environ, "NO_COLOR": "1"}
    if env:
        exec_env.update(env)

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=exec_env,
    )
    return result


def get_file_ownership(file_path: Path) -> tuple[int, int]:
    """Get file UID and GID on Unix systems.

    Args:
        file_path: Path to file

    Returns:
        Tuple of (uid, gid)

    Raises:
        NotImplementedError: On Windows
    """
    if platform.system() == "Windows":
        raise NotImplementedError("File ownership not available on Windows")

    file_stat = file_path.stat()
    return (file_stat.st_uid, file_stat.st_gid)
