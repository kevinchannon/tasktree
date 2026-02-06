"""Docker integration for Task Tree.

Provides Docker image building and container execution capabilities.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from pathspec import PathSpec

try:
    import pathspec
except ImportError:
    pathspec = None  # type: ignore

if TYPE_CHECKING:
    from tasktree.logging import Logger
    from tasktree.parser import Runner
    from tasktree.process_runner import ProcessRunner


class DockerError(Exception):
    """
    Raised when Docker operations fail.
    @athena: 876629e35765
    """

    pass


class DockerManager:
    """
    Manages Docker image building and container execution.
    @athena: f8f5c2693d84
    """

    def __init__(self, project_root: Path, logger: Logger):
        """
        Initialize Docker manager.

        Args:
            project_root: Root directory of the project (where tasktree.yaml is located)
            logger: Logger instance for debug/trace messages
        @athena: eb7d4c5a27aa
        """
        self._project_root = project_root
        self._logger = logger
        self._built_images: dict[
            str, tuple[str, str]
        ] = {}  # env_name -> (image_tag, image_id) cache

    @staticmethod
    def _should_add_user_flag() -> bool:
        """
        Check if --user flag should be added to docker run.

        Returns False on Windows (where Docker Desktop handles UID mapping automatically).
        Returns True on Linux/macOS where os.getuid() and os.getgid() are available.

        Returns:
        True if --user flag should be added, False otherwise
        @athena: c5932076dfda
        """
        # Skip on Windows - Docker Desktop handles UID mapping differently
        if platform.system() == "Windows":
            return False

        # Check if os.getuid() and os.getgid() are available (Linux/macOS)
        return hasattr(os, "getuid") and hasattr(os, "getgid")

    def ensure_image_built(
        self, env: Runner, process_runner: ProcessRunner
    ) -> tuple[str, str]:
        """
        Build Docker image if not already built this invocation.

        Args:
        env: Runner definition with dockerfile and context
        process_runner: ProcessRunner instance for subprocess execution

        Returns:
        Tuple of (image_tag, image_id)
        - image_tag: Tag like "tt-env-builder"
        - image_id: Full image ID like "sha256:abc123..."

        Raises:
        DockerError: If docker command not available or build fails
        @athena: 42b53d2685e0
        """
        # Check if already built this invocation
        if env.name in self._built_images:
            tag, image_id = self._built_images[env.name]
            return tag, image_id

        # Check if docker is available
        self._check_docker_available()

        # Resolve paths
        dockerfile_path = self._project_root / env.dockerfile
        context_path = self._project_root / env.context

        # Log resolved paths for debugging
        self._logger.debug(
            f"Resolved paths for runner '{env.name}': "
            f"dockerfile='{dockerfile_path}' (from '{env.dockerfile}'), "
            f"context='{context_path}' (from '{env.context}')"
        )

        # Generate image tag
        image_tag = f"tt-env-{env.name}"

        # Build the image
        try:
            docker_build_cmd = [
                "docker",
                "build",
                "-t",
                image_tag,
                "-f",
                str(dockerfile_path),
            ]

            # Add build args if environment has them (docker environments use dict for args)
            if isinstance(env.args, dict):
                for arg_name, arg_value in env.args.items():
                    docker_build_cmd.extend(["--build-arg", f"{arg_name}={arg_value}"])

            docker_build_cmd.append(str(context_path))

            process_runner.run(
                docker_build_cmd,
                check=True,
                capture_output=False,  # Show build output to user
            )
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"Failed to build Docker image for environment '{env.name}': "
                f"docker build exited with code {e.returncode}"
            ) from e
        except FileNotFoundError:
            raise DockerError(
                "Docker command not found. Please install Docker and ensure it's in your PATH."
            )

        # Get the image ID
        image_id = self._get_image_id(image_tag)

        # Cache both tag and ID
        self._built_images[env.name] = (image_tag, image_id)
        return image_tag, image_id

    def run_in_container(
        self,
        env: Environment,
        cmd: str,
        working_dir: Path,
        container_working_dir: str | None,
        process_runner: ProcessRunner,
    ) -> subprocess.CompletedProcess:
        """
        Execute command inside Docker container.

        Args:
        env: Runner definition
        cmd: Command to execute
        working_dir: Host working directory (for resolving relative volume paths)
        container_working_dir: Working directory inside container, or None to use Dockerfile's WORKDIR
        process_runner: ProcessRunner instance to use for subprocess execution

        Returns:
        CompletedProcess from subprocess.run

        Raises:
        DockerError: If docker run fails
        @athena: ef024ea2c182
        """
        # Ensure image is built (returns tag and ID)
        image_tag, image_id = self.ensure_image_built(env, process_runner)

        # Build docker run command
        docker_cmd = ["docker", "run", "--rm"]

        # Add user mapping (run as current host user) unless explicitly disabled or on Windows
        if not env.run_as_root and self._should_add_user_flag():
            uid = os.getuid()
            gid = os.getgid()
            docker_cmd.extend(["--user", f"{uid}:{gid}"])

        docker_cmd.extend(env.extra_args)

        # Add volume mounts
        for volume in env.volumes:
            # Resolve volume paths
            resolved_volume = self._resolve_volume_mount(volume)
            docker_cmd.extend(["-v", resolved_volume])

        # Add port mappings
        for port in env.ports:
            docker_cmd.extend(["-p", port])

        # Add environment variables
        for var_name, var_value in env.env_vars.items():
            docker_cmd.extend(["-e", f"{var_name}={var_value}"])

        # Add working directory
        if container_working_dir:
            docker_cmd.extend(["-w", container_working_dir])

        # Add image tag
        docker_cmd.append(image_tag)

        # Add shell and command
        shell = env.shell or "sh"
        shell_args = (
            env.args or [] if isinstance(env.args, list) else list(env.args.values())
        )
        docker_cmd.extend([shell, *shell_args, "-c", cmd])

        # Execute
        try:
            result = process_runner.run(
                docker_cmd,
                cwd=working_dir,
                check=True,
                capture_output=False,  # Stream output to terminal
            )
            return result
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"Docker container execution failed with exit code {e.returncode}"
            ) from e

    def _resolve_volume_mount(self, volume: str) -> str:
        """
        Resolve volume mount specification.

        Handles:
        - Relative paths (resolved relative to project_root)
        - Home directory expansion (~)
        - Absolute paths (used as-is)

        Args:
        volume: Volume specification (e.g., "./src:/workspace/src" or "~/.cargo:/root/.cargo")

        Returns:
        Resolved volume specification with absolute host path
        @athena: c7661050443e
        """
        if ":" not in volume:
            raise ValueError(
                f"Invalid volume specification: '{volume}'. "
                f"Format should be 'host_path:container_path'"
            )

        host_path, container_path = volume.split(":", 1)

        # Expand home directory
        if host_path.startswith("~"):
            host_path = os.path.expanduser(host_path)
            resolved_host_path = Path(host_path)
        # Resolve relative paths
        elif not Path(host_path).is_absolute():
            resolved_host_path = self._project_root / host_path
        # Absolute paths used as-is
        else:
            resolved_host_path = Path(host_path)

        return f"{resolved_host_path}:{container_path}"

    @staticmethod
    def _check_docker_available() -> None:
        """
        Check if docker command is available.

        Raises:
        DockerError: If docker is not available
        @athena: 8deaf8c5c05e
        """
        try:
            subprocess.run(
                ["docker", "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise DockerError(
                "Docker is not available. Please install Docker and ensure it's running.\n"
                "Visit https://docs.docker.com/get-docker/ for installation instructions."
            )

    @staticmethod
    def _get_image_id(image_tag: str) -> str:
        """
        Get the full image ID for a given tag.

        Args:
        image_tag: Docker image tag (e.g., "tt-env-builder")

        Returns:
        Full image ID (e.g., "sha256:abc123def456...")

        Raises:
        DockerError: If cannot inspect image
        @athena: 9e5aa77003ee
        """
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format={{.Id}}", image_tag],
                check=True,
                capture_output=True,
                text=True,
            )
            image_id = result.stdout.strip()
            return image_id
        except subprocess.CalledProcessError as e:
            raise DockerError(f"Failed to inspect image {image_tag}: {e.stderr}")


def is_docker_runner(env: Runner) -> bool:
    """
    Check if runner is Docker-based.

    Args:
    env: Runner to check

    Returns:
    True if runner has a dockerfile field, False otherwise
    @athena: 1ffd255a4e90
    """
    return bool(env.dockerfile)


def resolve_container_working_dir(
    env_working_dir: str, task_working_dir: str
) -> str | None:
    """
    Resolve working directory inside container.

    Combines environment's working_dir with task's working_dir:
    - If task specifies working_dir: container_dir = env_working_dir / task_working_dir
    - If task doesn't specify: container_dir = env_working_dir
    - If neither specify: container_dir = None (use Dockerfile's WORKDIR)

    Args:
    env_working_dir: Working directory from environment definition
    task_working_dir: Working directory from task definition

    Returns:
    Resolved working directory path, or None if neither specified
    @athena: bb13d00dd07d
    """
    if not env_working_dir and not task_working_dir:
        return None

    if not task_working_dir:
        return env_working_dir

    # Combine paths
    if env_working_dir:
        # Join paths using POSIX separator (works inside Linux containers)
        return f"{env_working_dir.rstrip('/')}/{task_working_dir.lstrip('/')}"
    else:
        return f"/{task_working_dir.lstrip('/')}"


def parse_dockerignore(dockerignore_path: Path) -> PathSpec | None:
    """
    Parse .dockerignore file into pathspec matcher.

    Args:
    dockerignore_path: Path to .dockerignore file

    Returns:
    PathSpec object for matching, or None if file doesn't exist or pathspec not available
    @athena: 13fca9ee5a73
    """
    if pathspec is None:
        # pathspec library not available - can't parse .dockerignore
        return None

    if not dockerignore_path.exists():
        return pathspec.PathSpec([])  # Empty matcher

    try:
        with open(dockerignore_path, "r") as f:
            spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
        return spec
    except Exception:
        # Invalid patterns - return empty matcher rather than failing
        return pathspec.PathSpec([])


def context_changed_since(
    context_path: Path,
    dockerignore_path: Path | None,
    last_run_time: float,
) -> bool:
    """
    Check if any file in Docker build context has changed since last run.

    Uses early-exit optimization: stops on first changed file found.

    Args:
    context_path: Path to Docker build context directory
    dockerignore_path: Optional path to .dockerignore file
    last_run_time: Unix timestamp of last task run

    Returns:
    True if any file changed, False otherwise
    @athena: 556acb1ed6ca
    """
    # Parse .dockerignore
    dockerignore_spec = None
    if dockerignore_path:
        dockerignore_spec = parse_dockerignore(dockerignore_path)

    # Walk context directory
    for file_path in context_path.rglob("*"):
        if not file_path.is_file():
            continue

        # Check if file matches .dockerignore patterns
        if dockerignore_spec:
            try:
                relative_path = file_path.relative_to(context_path)
                if dockerignore_spec.match_file(str(relative_path)):
                    continue  # Skip ignored files
            except ValueError:
                # File not relative to context (shouldn't happen with rglob)
                continue

        # Check if file changed (early exit)
        try:
            if file_path.stat().st_mtime > last_run_time:
                return True  # Found a changed file
        except (OSError, FileNotFoundError):
            # File might have been deleted - consider it changed
            return True

    return False  # No changes found


def extract_from_images(dockerfile_content: str) -> list[tuple[str, str | None]]:
    """
    Extract image references from FROM lines in Dockerfile.

    Args:
    dockerfile_content: Content of Dockerfile

    Returns:
    List of (image_reference, digest) tuples where digest may be None for unpinned images
    Example: [("rust:1.75", None), ("rust", "sha256:abc123...")]
    @athena: de0d013fdd05
    """
    # Regex pattern to match FROM lines
    # Handles: FROM [--platform=...] image[:tag][@digest] [AS alias]
    from_pattern = re.compile(
        r"^\s*FROM\s+"  # FROM keyword
        r"(?:--platform=\S+\s+)?"  # Optional platform flag
        r"([^\s@]+)"  # Image name (possibly with :tag)
        r"(?:@(sha256:[a-f0-9]+))?"  # Optional @digest
        r"(?:\s+AS\s+\w+)?"  # Optional AS alias
        r"\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    matches = from_pattern.findall(dockerfile_content)
    return [(image, digest if digest else None) for image, digest in matches]


def check_unpinned_images(dockerfile_content: str) -> list[str]:
    """
    Check for unpinned base images in Dockerfile.

    Args:
    dockerfile_content: Content of Dockerfile

    Returns:
    List of unpinned image references (images without @sha256:... digests)
    @athena: 58cc6de8fc96
    """
    images = extract_from_images(dockerfile_content)
    return [image for image, digest in images if digest is None]


def parse_base_image_digests(dockerfile_content: str) -> list[str]:
    """
    Parse pinned base image digests from Dockerfile.

    Args:
    dockerfile_content: Content of Dockerfile

    Returns:
    List of digests (e.g., ["sha256:abc123...", "sha256:def456..."])
    @athena: c4d1da6b067c
    """
    images = extract_from_images(dockerfile_content)
    return [digest for _image, digest in images if digest is not None]
