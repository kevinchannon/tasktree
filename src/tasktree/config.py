"""
Configuration file parsing for default runner definitions.
@athena: to-be-generated
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import platformdirs
import yaml

from tasktree.parser import Runner

__all__ = [
    "get_user_config_path",
    "get_machine_config_path",
    "find_project_config",
    "parse_config_file",
    "ConfigError",
]


def get_machine_config_path() -> Path:
    """
    Get the path to the machine-level (system-wide) configuration file.

    Uses platformdirs to determine the appropriate site config directory
    for the current platform, then appends 'tasktree/config.yml'.

    Returns:
        Path to the machine config file (may not exist)

    Example:
        >>> machine_config = get_machine_config_path()
        >>> if machine_config.exists():
        ...     runner = parse_config_file(machine_config)

    @athena: to-be-generated
    """
    config_dir = Path(platformdirs.site_config_dir("tasktree"))
    return config_dir / "config.yml"


def get_user_config_path() -> Path:
    """
    Get the path to the user-level configuration file.

    Uses platformdirs to determine the appropriate user config directory
    for the current platform, then appends 'tasktree/config.yml'.

    Returns:
        Path to the user config file (may not exist)

    Example:
        >>> user_config = get_user_config_path()
        >>> if user_config.exists():
        ...     runner = parse_config_file(user_config)

    @athena: to-be-generated
    """
    config_dir: Path = Path(platformdirs.user_config_dir("tasktree"))
    return config_dir / "config.yml"


def find_project_config(start_dir: Path) -> Optional[Path]:
    """
    Walk up the directory tree from start_dir to find .tasktree-config.yml.

    Args:
        start_dir: Directory to start searching from

    Returns:
        Path to .tasktree-config.yml if found, None otherwise

    Example:
        >>> config_path = find_project_config(Path.cwd())
        >>> if config_path:
        ...     runner = parse_config_file(config_path)

    @athena: to-be-generated
    """
    try:
        current = start_dir.resolve()
    except (OSError, RuntimeError) as e:
        # resolve() can raise OSError on invalid paths or RuntimeError on symlink loops
        # Return None to indicate config not found
        return None

    # Walk up the directory tree with a safety limit
    # Maximum depth of 100 prevents infinite loops in edge cases
    max_depth = 100
    for _ in range(max_depth):
        try:
            config_path = current / ".tasktree-config.yml"
            if config_path.exists():
                return config_path
        except (OSError, PermissionError):
            # If we can't check existence (permission denied or other OS error),
            # skip this directory and continue up the tree
            pass

        # Check if we've reached a filesystem boundary
        try:
            parent = current.parent
        except (OSError, RuntimeError):
            # If we can't get the parent, stop here
            break

        if parent == current:
            # We've reached the root
            break

        current = parent

    return None


class ConfigError(Exception):
    """
    Raised when a configuration file is invalid.
    @athena: to-be-generated
    """

    pass


def parse_config_file(path: Path) -> Optional[Runner]:
    """
    Parse a tasktree configuration file and return the default runner if defined.

    Config files must have a single runner named 'default' if the 'runners' key exists.
    Empty files or files without a 'runners' key are valid and return None.

    Args:
        path: Path to the configuration file

    Returns:
        Runner object for the default runner, or None if no default is defined
        or the file doesn't exist

    Raises:
        ConfigError: If the config file is invalid (malformed YAML, invalid structure,
                     multiple runners, etc.)

    Example:
        >>> runner = parse_config_file(Path(".tasktree-config.yml"))
        >>> if runner:
        ...     print(f"Using {runner.shell} shell")

    Config File Examples:

        Project-level config (.tasktree-config.yml):
            ```yaml
            runners:
              default:
                dockerfile: docker/Dockerfile
                context: .
                volumes:
                  - ./data:/workspace/data
            ```

        User-level config (~/.config/tasktree/config.yml):
            ```yaml
            runners:
              default:
                # Relative paths work if your projects use consistent structure
                dockerfile: docker/Dockerfile
                context: .
            ```

        Shell runner config:
            ```yaml
            runners:
              default:
                shell: /bin/bash
                preamble: |
                  set -euo pipefail
                  export PATH=$PATH:$HOME/bin
            ```

    Note:
        Relative paths in runner definitions (e.g., dockerfile, context) are stored
        as-is in the Runner object. Path resolution happens at task execution time
        in docker.py, where relative paths are resolved relative to the project root.
        This allows configs to be portable across machines.

        Path Resolution:
        - Relative paths (e.g., "docker/Dockerfile") are stored as-is
        - Absolute paths are stored as-is
        - Resolution happens at task execution time in docker.py
        - If a relative path cannot be resolved (e.g., dockerfile doesn't exist),
          Docker will fail with an error indicating the file was not found

        For user-level and machine-level configs with relative paths, ensure that
        the relative paths are valid from the project root of projects where the
        config will be used.

    @athena: to-be-generated
    """
    # Return None if file doesn't exist (not an error)
    if not path.exists():
        return None

    try:
        with open(path, "r") as f:
            content = f.read()
    except (IOError, OSError) as e:
        # Permission errors or other I/O issues
        raise ConfigError(f"Error reading config file '{path}': {e}") from e

    # Empty file is valid (returns None)
    if not content.strip():
        return None

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ConfigError(f"Error parsing YAML in config file '{path}': {e}") from e

    # None or empty YAML is valid (returns None)
    if data is None:
        return None

    # If no 'runners' key, return None (valid but no default)
    if "runners" not in data:
        return None

    runners_data = data["runners"]

    # Validate that runners is a dict
    if not isinstance(runners_data, dict):
        raise ConfigError(
            f"Error in config file '{path}': 'runners' must be a dictionary"
        )

    # Check if 'default' runner exists
    if "default" not in runners_data:
        # If runners key exists but no default, error
        raise ConfigError(
            f"Error in config file '{path}': 'runners' section must contain "
            f"exactly one runner named 'default'"
        )

    # Check for multiple runners (only 'default' is allowed)
    runner_names = [name for name in runners_data.keys() if name != "default"]
    if runner_names:
        raise ConfigError(
            f"Error in config file '{path}': Config files may only contain a "
            f"runner named 'default', but found: {', '.join(runner_names)}"
        )

    runner_config = runners_data["default"]

    # Validate that runner config is a dict
    if not isinstance(runner_config, dict):
        raise ConfigError(
            f"Error in config file '{path}': Runner 'default' must be a dictionary"
        )

    # Parse runner fields with type validation
    shell = runner_config.get("shell", "")
    if not isinstance(shell, str):
        raise ConfigError(
            f"Error in config file '{path}': Field 'shell' must be a string"
        )

    args = runner_config.get("args", [])
    if not isinstance(args, list):
        raise ConfigError(
            f"Error in config file '{path}': Field 'args' must be a list"
        )

    preamble = runner_config.get("preamble", "")
    if not isinstance(preamble, str):
        raise ConfigError(
            f"Error in config file '{path}': Field 'preamble' must be a string"
        )

    working_dir = runner_config.get("working_dir", "")
    if not isinstance(working_dir, str):
        raise ConfigError(
            f"Error in config file '{path}': Field 'working_dir' must be a string"
        )

    # Parse Docker-specific fields with type validation
    dockerfile = runner_config.get("dockerfile", "")
    if not isinstance(dockerfile, str):
        raise ConfigError(
            f"Error in config file '{path}': Field 'dockerfile' must be a string"
        )

    context = runner_config.get("context", "")
    if not isinstance(context, str):
        raise ConfigError(
            f"Error in config file '{path}': Field 'context' must be a string"
        )

    volumes = runner_config.get("volumes", [])
    if not isinstance(volumes, list):
        raise ConfigError(
            f"Error in config file '{path}': Field 'volumes' must be a list"
        )

    ports = runner_config.get("ports", [])
    if not isinstance(ports, list):
        raise ConfigError(
            f"Error in config file '{path}': Field 'ports' must be a list"
        )

    env_vars = runner_config.get("env_vars", {})
    if not isinstance(env_vars, dict):
        raise ConfigError(
            f"Error in config file '{path}': Field 'env_vars' must be a dictionary"
        )

    extra_args = runner_config.get("extra_args", [])
    if not isinstance(extra_args, list):
        raise ConfigError(
            f"Error in config file '{path}': Field 'extra_args' must be a list"
        )

    run_as_root = runner_config.get("run_as_root", False)
    if not isinstance(run_as_root, bool):
        raise ConfigError(
            f"Error in config file '{path}': Field 'run_as_root' must be a boolean"
        )

    # Validate runner type (must have either shell or dockerfile)
    if not shell and not dockerfile:
        raise ConfigError(
            f"Error in config file '{path}': Runner 'default' must specify either "
            f"'shell' (for shell runners) or 'dockerfile' (for Docker runners)"
        )

    # Note: Path validation (checking if dockerfile/context exist) is deferred to
    # execution time, as per the spec: "Validation occurs at task execution time"
    # This allows configs to reference files that may not exist on all machines

    # Create and return the Runner object
    return Runner(
        name="default",
        shell=shell,
        args=args,
        preamble=preamble,
        dockerfile=dockerfile,
        context=context,
        volumes=volumes,
        ports=ports,
        env_vars=env_vars,
        working_dir=working_dir,
        extra_args=extra_args,
        run_as_root=run_as_root,
    )
