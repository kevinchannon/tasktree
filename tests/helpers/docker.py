import subprocess


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
        return result.returncode == 0 and "OSType: linux" in result.stdout
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False
