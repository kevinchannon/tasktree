"""Docker integration for Task Tree.

Provides Docker image building and container execution capabilities.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import pathspec
except ImportError:
    pathspec = None  # type: ignore

if TYPE_CHECKING:
    from tasktree.parser import Environment


class DockerError(Exception):
    """Raised when Docker operations fail."""

    pass


class DockerManager:
    """Manages Docker image building and container execution."""

    def __init__(self, project_root: Path):
        """Initialize Docker manager.

        Args:
            project_root: Root directory of the project (where tasktree.yaml is located)
        """
        self._project_root = project_root
        self._built_images: dict[str, tuple[str, str]] = {}  # env_name -> (image_tag, image_id) cache

    def ensure_image_built(self, env: Environment) -> tuple[str, str]:
        """Build Docker image if not already built this invocation.

        Args:
            env: Environment definition with dockerfile and context

        Returns:
            Tuple of (image_tag, image_id)
            - image_tag: Tag like "tt-env-builder"
            - image_id: Full image ID like "sha256:abc123..."

        Raises:
            DockerError: If docker command not available or build fails
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

        # Generate image tag
        image_tag = f"tt-env-{env.name}"

        # Build the image
        try:
            subprocess.run(
                [
                    "docker",
                    "build",
                    "-t",
                    image_tag,
                    "-f",
                    str(dockerfile_path),
                    str(context_path),
                ],
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
        container_working_dir: str,
    ) -> subprocess.CompletedProcess:
        """Execute command inside Docker container.

        Args:
            env: Environment definition
            cmd: Command to execute
            working_dir: Host working directory (for resolving relative volume paths)
            container_working_dir: Working directory inside container

        Returns:
            CompletedProcess from subprocess.run

        Raises:
            DockerError: If docker run fails
        """
        # Ensure image is built (returns tag and ID)
        image_tag, image_id = self.ensure_image_built(env)

        # Build docker run command
        docker_cmd = ["docker", "run", "--rm"]

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
        docker_cmd.extend([shell, "-c", cmd])

        # Execute
        try:
            result = subprocess.run(
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
        """Resolve volume mount specification.

        Handles:
        - Relative paths (resolved relative to project_root)
        - Home directory expansion (~)
        - Absolute paths (used as-is)

        Args:
            volume: Volume specification (e.g., "./src:/workspace/src" or "~/.cargo:/root/.cargo")

        Returns:
            Resolved volume specification with absolute host path
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

    def _check_docker_available(self) -> None:
        """Check if docker command is available.

        Raises:
            DockerError: If docker is not available
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

    def _get_image_id(self, image_tag: str) -> str:
        """Get the full image ID for a given tag.

        Args:
            image_tag: Docker image tag (e.g., "tt-env-builder")

        Returns:
            Full image ID (e.g., "sha256:abc123def456...")

        Raises:
            DockerError: If cannot inspect image
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


def is_docker_environment(env: Environment) -> bool:
    """Check if environment is Docker-based.

    Args:
        env: Environment to check

    Returns:
        True if environment has a dockerfile field, False otherwise
    """
    return bool(env.dockerfile)


def resolve_container_working_dir(
    env_working_dir: str, task_working_dir: str
) -> str:
    """Resolve working directory inside container.

    Combines environment's working_dir with task's working_dir:
    - If task specifies working_dir: container_dir = env_working_dir / task_working_dir
    - If task doesn't specify: container_dir = env_working_dir
    - If neither specify: container_dir = "/" (Docker default)

    Args:
        env_working_dir: Working directory from environment definition
        task_working_dir: Working directory from task definition

    Returns:
        Resolved working directory path
    """
    if not env_working_dir and not task_working_dir:
        return "/"

    if not task_working_dir:
        return env_working_dir

    # Combine paths
    if env_working_dir:
        # Join paths using POSIX separator (works inside Linux containers)
        return f"{env_working_dir.rstrip('/')}/{task_working_dir.lstrip('/')}"
    else:
        return f"/{task_working_dir.lstrip('/')}"


def parse_dockerignore(dockerignore_path: Path) -> "pathspec.PathSpec | None":
    """Parse .dockerignore file into pathspec matcher.

    Args:
        dockerignore_path: Path to .dockerignore file

    Returns:
        PathSpec object for matching, or None if file doesn't exist or pathspec not available
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
    """Check if any file in Docker build context has changed since last run.

    Uses early-exit optimization: stops on first changed file found.

    Args:
        context_path: Path to Docker build context directory
        dockerignore_path: Optional path to .dockerignore file
        last_run_time: Unix timestamp of last task run

    Returns:
        True if any file changed, False otherwise
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
    """Extract image references from FROM lines in Dockerfile.

    Args:
        dockerfile_content: Content of Dockerfile

    Returns:
        List of (image_reference, digest) tuples where digest may be None for unpinned images
        Example: [("rust:1.75", None), ("rust", "sha256:abc123...")]
    """
    # Regex pattern to match FROM lines
    # Handles: FROM [--platform=...] image[:tag][@digest] [AS alias]
    from_pattern = re.compile(
        r"^\s*FROM\s+"  # FROM keyword
        r"(?:--platform=[^\s]+\s+)?"  # Optional platform flag
        r"([^\s@]+)"  # Image name (possibly with :tag)
        r"(?:@(sha256:[a-f0-9]+))?"  # Optional @digest
        r"(?:\s+AS\s+\w+)?"  # Optional AS alias
        r"\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    matches = from_pattern.findall(dockerfile_content)
    return [(image, digest if digest else None) for image, digest in matches]


def check_unpinned_images(dockerfile_content: str) -> list[str]:
    """Check for unpinned base images in Dockerfile.

    Args:
        dockerfile_content: Content of Dockerfile

    Returns:
        List of unpinned image references (images without @sha256:... digests)
    """
    images = extract_from_images(dockerfile_content)
    return [image for image, digest in images if digest is None]


def parse_base_image_digests(dockerfile_content: str) -> list[str]:
    """Parse pinned base image digests from Dockerfile.

    Args:
        dockerfile_content: Content of Dockerfile

    Returns:
        List of digests (e.g., ["sha256:abc123...", "sha256:def456..."])
    """
    images = extract_from_images(dockerfile_content)
    return [digest for _image, digest in images if digest is not None]
