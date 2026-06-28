"""Docker integration for Task Tree.

Provides Docker image building and container execution capabilities.
"""

from __future__ import annotations

import os
import platform
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from tasktree.interpreter import INTERPRETER_LOOKUP, Interpreter
from tasktree.temp_script import TempScript

if TYPE_CHECKING:
    from tasktree.logging import Logger
    from tasktree.parser import Runner
    from tasktree.process_runner import ProcessRunner


class DockerError(Exception):
    """
    Raised when Docker operations fail.
    """

    pass


def _is_windows_shell(shell: str) -> bool:
    """
    Determine if the specified shell is a Windows shell.

    Args:
        shell: Shell name or path (e.g., "bash", "sh", "cmd.exe", "powershell")

    Returns:
        True if shell is Windows-based (cmd.exe or powershell), False otherwise
    """
    shell_lower = shell.lower()
    # Check for Windows shells (cmd.exe, cmd, powershell.exe, powershell, pwsh)
    return any(
        win_shell in shell_lower
        for win_shell in ["cmd.exe", "cmd", "powershell", "pwsh"]
    )


def _get_container_script_extension(shell: str) -> str:
    """
    Get the appropriate script file extension for the container shell.

    Args:
        shell: Shell to use in container (e.g., "bash", "sh", "cmd.exe", "powershell")

    Returns:
        File extension including the dot (e.g., ".sh", ".bat", ".ps1")
    """
    if _is_windows_shell(shell):
        shell_lower = shell.lower()
        if "powershell" in shell_lower or "pwsh" in shell_lower:
            return ".ps1"
        else:
            return ".bat"
    return ".sh"


def _container_interpreter(env: "Runner") -> Interpreter:
    """Resolve the Interpreter used to run a script inside a container.

    Precedence: the runner's explicit ``interpreter``, then the interpreter
    named by ``shell.cmd[0]`` (inline flags like ``-c`` are not part of
    script-file execution), then the container default (sh).
    """
    if env.default_interpreter:
        return Interpreter.from_name(env.default_interpreter)
    if env.shell is not None and env.shell.cmd:
        name = env.shell.cmd[0]
        if name in INTERPRETER_LOOKUP:
            return Interpreter.from_name(name)
        return Interpreter.from_shell_cmd([name])
    return Interpreter.container_default()


class DockerManager:
    """
    Manages Docker image building and container execution.
    """

    def __init__(self, project_root: Path, logger: Logger):
        """
        Initialize Docker manager.

        Args:
            project_root: Root directory of the project (where tasktree.yaml is located)
            logger: Logger instance for debug/trace messages
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
        """
        # Skip on Windows - Docker Desktop handles UID mapping differently
        return platform.system() != "Windows"

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

            # Add build args if environment has them
            docker_build_cmd.extend(env.args.build)

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
        """
        # Ensure image is built (returns tag and ID)
        image_tag, image_id = self.ensure_image_built(env, process_runner)

        # Resolve the interpreter for this container and the preamble to prepend.
        interpreter = _container_interpreter(env)
        preamble = env.shell.preamble if env.shell is not None else ""

        # Script extension and shebang behaviour come from the interpreter:
        # .sh for Unix shells (shebang-friendly), .bat/.ps1 for Windows shells.
        script_ext = interpreter.script_extension
        use_shebang = script_ext not in (".bat", ".ps1")

        # Generate unique container script path to avoid collisions between concurrent executions
        script_id = uuid.uuid4()
        script_filename = f"tt-script-{script_id}{script_ext}"
        container_script_path = f"/tmp/{script_filename}"

        # Create temp script on host with preamble and command, then mount into container.
        # The script extension and shebang behavior are determined by the container shell type,
        # not the host platform (e.g., Windows containers use .bat even on Linux hosts).
        try:
            with TempScript(
                logger=self._logger,
                cmd=cmd,
                preamble=preamble,
                shell=interpreter.invocation_cmd[0],
                script_extension=script_ext,
                use_shebang=use_shebang,
            ) as script_path:
                # Build docker run command from the shared flags (user mapping,
                # run args, volume mounts incl. the auto repo-mount, ports, env).
                docker_cmd = ["docker", "run", "--rm"] + self._base_run_flags(env)

                # Mount temp script into container at unique path (read-only for security)
                docker_cmd.extend(["-v", f"{script_path}:{container_script_path}:ro"])

                # Add working directory
                if container_working_dir:
                    docker_cmd.extend(["-w", container_working_dir])

                # Add image tag
                docker_cmd.append(image_tag)

                # Execute the script directly with the interpreter's invocation
                # (no inline flags like -c; those are for inline commands, not
                # script-file execution).
                docker_cmd.extend(
                    list(interpreter.invocation_cmd) + [container_script_path]
                )

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
        except OSError as e:
            raise DockerError(
                f"Failed to create temporary script for Docker execution: {e}"
            ) from e

    def _base_run_flags(self, env: Runner) -> list[str]:
        """
        Build the docker run flags shared by task execution and freshness probing.

        Covers user mapping, run args, the auto project-root mount, user-defined
        volumes, port mappings and environment variables -- everything that makes
        the container see the same filesystem the task runs against. Does NOT
        include the working directory, image tag, or the command to run.
        """
        flags: list[str] = []

        # Run as the current host user unless disabled or on Windows, so files
        # created in mounted volumes are owned by the host user (numeric mapping;
        # the user need not exist in the container).
        if not env.run_as_root and self._should_add_user_flag():
            flags.extend(["--user", f"{os.getuid()}:{os.getgid()}"])

        flags.extend(env.args.run)

        # Auto-mount the project root at its own (resolved) path unless the user
        # already maps it. See run_in_container for the rationale on resolve().
        if not self._project_root_is_mounted(env.volumes):
            root = self._project_root.resolve()
            flags.extend(["-v", f"{root}:{root}"])

        for volume in env.volumes:
            flags.extend(["-v", self._resolve_volume_mount(volume)])

        for port in env.ports:
            flags.extend(["-p", port])

        for var_name, var_value in env.env_vars.items():
            flags.extend(["-e", f"{var_name}={var_value}"])

        return flags

    def capture_in_container(
        self, env: Runner, argv: list[str], process_runner: ProcessRunner
    ) -> str:
        """
        Run a command inside the container and capture its stdout.

        Uses the same image and mounts as task execution (via _base_run_flags) so
        that filesystem queries (e.g. freshness probing) resolve paths exactly as
        the task itself would. Intended for short internal commands, not task
        execution, so output is captured rather than streamed.

        Args:
            env: Runner definition
            argv: Command (and args) to run in the container
            process_runner: ProcessRunner used to build the image if needed

        Returns:
            The command's stdout as a string.

        Raises:
            DockerError: If the docker command fails.
        """
        image_tag, _ = self.ensure_image_built(env, process_runner)
        docker_cmd = (
            ["docker", "run", "--rm"]
            + self._base_run_flags(env)
            + [image_tag]
            + list(argv)
        )
        try:
            result = subprocess.run(
                docker_cmd, check=True, capture_output=True, text=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"Docker freshness probe failed with exit code {e.returncode}: {e.stderr}"
            ) from e

    def _project_root_is_mounted(self, volumes: list[str]) -> bool:
        """
        Check whether any volume already bind-mounts the project root.

        Compares the resolved host side of each volume against the project root
        so we don't add a duplicate same-path mount when the user has already
        mapped the project root (at its own path or a different container path).

        Args:
            volumes: Volume specifications from the runner definition

        Returns:
            True if some volume's host path is the project root, False otherwise
        """
        root = self._project_root.resolve()
        for volume in volumes:
            host_path = self._resolve_volume_mount(volume).split(":", 1)[0]
            try:
                if Path(host_path).resolve() == root:
                    return True
            except OSError:
                continue
        return False

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
        """
        if ":" not in volume:
            raise ValueError(
                f"Invalid volume specification: '{volume}'. "
                f"Format should be 'host_path:container_path'"
            )

        host_path, container_path = volume.split(":", 1)

        # Expand home directory (preserve as string to keep forward slashes on all platforms)
        if host_path.startswith("~"):
            host_path = os.path.expanduser(host_path)
        # Treat paths starting with / as absolute (POSIX-style, used in Docker volume specs)
        # and paths that are absolute on the native OS as absolute too
        elif not host_path.startswith("/") and not Path(host_path).is_absolute():
            # Relative path: resolve relative to project root
            host_path = str(self._project_root / host_path)
        # Absolute paths (POSIX /... or native OS absolute) used as-is

        return f"{host_path}:{container_path}"

    @staticmethod
    def _check_docker_available() -> None:
        """
        Check if docker command is available.

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
        """
        try:
            return _run_docker_inspect(image_tag)
        except subprocess.CalledProcessError as e:
            raise DockerError(f"Failed to inspect image {image_tag}: {e.stderr}")

    @staticmethod
    def image_content_fingerprint(image_tag: str) -> str:
        """
        Return a content fingerprint for a built image.

        The fingerprint is the image's RootFS layer digests, which are
        content-addressed: it is stable across identical rebuilds but changes
        whenever the image content does (e.g. a Dockerfile edit or a new base
        image). This is used to detect environment changes that should force a
        task re-run. We deliberately do NOT use the image Id, which BuildKit
        regenerates on every rebuild even when nothing changed.

        Args:
            image_tag: Docker image tag (e.g. "tt-env-builder")

        Returns:
            A stable fingerprint string for the image's content.

        Raises:
            DockerError: If the image cannot be inspected.
        """
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{json .RootFS.Layers}}", image_tag],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"Failed to fingerprint image {image_tag}: {e.stderr}"
            )


def is_docker_runner(env: Runner) -> bool:
    """
    Check if runner is Docker-based.

    Args:
    env: Runner to check

    Returns:
    True if runner has a dockerfile field, False otherwise
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


def _run_docker_inspect(image_name: str) -> str:
    """
    Run 'docker inspect --format={{.Id}}' and return the stripped image ID.

    Args:
    image_name: Docker image reference (e.g., "python:3.11", "tt-env-builder")

    Returns:
    Stripped image ID string

    Raises:
    subprocess.CalledProcessError: If image not found or inspect fails
    FileNotFoundError: If docker is not installed
    PermissionError: If docker daemon is unavailable
    """
    result = subprocess.run(
        ["docker", "inspect", "--format={{.Id}}", image_name],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
