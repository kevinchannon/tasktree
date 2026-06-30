"""Task execution and staleness detection."""

from __future__ import annotations

import io
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tasktree import docker as docker_module
from tasktree.config import ConfigError
from tasktree.freshness import FreshnessProbe, HostProbe, RunnerProbe
from tasktree.graph import (
    get_implicit_inputs,
    resolve_execution_order,
    resolve_dependency_output_references,
    resolve_self_references,
)
from tasktree.hasher import hash_args, hash_task, make_cache_key
from tasktree.logging import Logger, LogLevel
from tasktree.parser import DockerArgs, Recipe, Task, Runner, platform_default_interpreter, container_default_interpreter
from tasktree.interpreter import Interpreter
from tasktree.process_runner import ProcessRunner, TaskOutputTypes
from tasktree.state import StateManager, TaskState
from tasktree.hasher import hash_runner_definition
from tasktree.temp_script import TempScript


def _supports_fileno(stream) -> bool:
    """Check if a stream has a working fileno() method."""
    try:
        stream.fileno()
        return True
    except (AttributeError, OSError, io.UnsupportedOperation):
        return False


def _extract_shebang_interpreter(shebang_line: str) -> str:
    """Extract the interpreter name from a shebang line.

    Examples:
        '#!/usr/bin/env bash' -> 'bash'
        '#!/bin/bash'         -> 'bash'
        '#!/usr/bin/python3'  -> 'python3'
    """
    path_part = shebang_line[2:].strip()
    parts = path_part.split()
    if not parts:
        return ""
    if os.path.basename(parts[0]) == "env" and len(parts) > 1:
        return parts[1]
    return os.path.basename(parts[0])


@dataclass
class TaskStatus:
    """
    Status of a task for execution planning.
    """

    task_name: str
    will_run: bool
    reason: str  # "fresh", "inputs_changed", "definition_changed",
    # "never_run", "no_inputs", "outputs_missing", "forced", "environment_changed"
    changed_files: list[str] = field(default_factory=list)
    last_run: datetime | None = None


class ExecutionError(Exception):
    """
    Raised when task execution fails.
    """

    pass


class Executor:
    """
    Executes tasks with incremental execution logic.
    """

    # Environment variable for tracking task call chain (recursion detection)
    TT_CALL_CHAIN_ENV_VAR = "TT_CALL_CHAIN"

    # Protected environment variables that cannot be overridden by exported args
    PROTECTED_ENV_VARS = {
        "PATH",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "PYTHONPATH",
        "HOME",
        "SHELL",
        "USER",
        "LOGNAME",
    }

    def __init__(
        self,
        recipe: Recipe,
        state_manager: StateManager,
        logger: Logger,
        process_runner_factory: Callable[[TaskOutputTypes, Logger], ProcessRunner],
    ):
        """
        Initialize executor.

        Args:
        recipe: Parsed recipe containing all tasks
        state_manager: State manager for tracking task execution
        logger_fn: Logger function for output (matches Console.print signature)
        process_runner_factory: Factory function for creating ProcessRunner instances
        """
        self.recipe = recipe
        self.state = state_manager
        self.logger = logger
        self._process_runner_factory = process_runner_factory
        self.docker_manager = docker_module.DockerManager(recipe.project_root, logger)

    @staticmethod
    def _has_regular_args(task: Task) -> bool:
        """
        Check if a task has any regular (non-exported) arguments.

        Args:
        task: Task to check

        Returns:
        True if task has at least one regular (non-exported) argument, False otherwise
        """
        if not task.args:
            return False

        # Check if any arg is not exported (doesn't start with $)
        for arg_spec in task.args:
            # Handle both string and dict arg specs
            if isinstance(arg_spec, str):
                # Remove default value part if present
                arg_name = arg_spec.split("=")[0].split(":")[0].strip()
                if not arg_name.startswith("$"):
                    return True
            elif isinstance(arg_spec, dict):
                # Dict format: { argname: { ... } } or { $argname: { ... } }
                for key in arg_spec.keys():
                    if not key.startswith("$"):
                        return True

        return False

    @staticmethod
    def _filter_regular_args(task: Task, task_args: dict[str, Any]) -> dict[str, Any]:
        """
        Filter task_args to only include regular (non-exported) arguments.

        Args:
        task: Task definition
        task_args: Dictionary of all task arguments

        Returns:
        Dictionary containing only regular (non-exported) arguments
        """
        if not task.args or not task_args:
            return {}

        # Build set of exported arg names (without the $ prefix)
        exported_names = set()
        for arg_spec in task.args:
            if isinstance(arg_spec, str):
                arg_name = arg_spec.split("=")[0].split(":")[0].strip()
                if arg_name.startswith("$"):
                    exported_names.add(arg_name[1:])  # Remove $ prefix
            elif isinstance(arg_spec, dict):
                for key in arg_spec.keys():
                    if key.startswith("$"):
                        exported_names.add(key[1:])  # Remove $ prefix

        # Filter out exported args
        return {k: v for k, v in task_args.items() if k not in exported_names}

    def _collect_early_builtin_variables(
        self, task: Task, timestamp: datetime
    ) -> dict[str, str]:
        """
        Collect built-in variables that don't depend on working_dir.

        These variables can be used in the working_dir field itself.

        Args:
        task: Task being executed
        timestamp: Timestamp when task started execution

        Returns:
        Dictionary mapping built-in variable names to their string values

        Raises:
        ExecutionError: If any built-in variable fails to resolve
        """
        import os

        builtin_vars = {
            # {{ tt.project_root }} - Absolute path to project root
            "project_root": str(self.recipe.project_root.resolve()),
            # {{ tt.recipe_dir }} - Absolute path to directory containing the recipe file
            "recipe_dir": str(self.recipe.recipe_path.parent.resolve()),
            # {{ tt.task_name }} - Name of currently executing task
            "task_name": task.name,
            # {{ tt.timestamp }} - ISO8601 timestamp when task started execution
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            # {{ tt.timestamp_unix }} - Unix epoch timestamp when task started
            "timestamp_unix": str(int(timestamp.timestamp())),
        }

        # {{ tt.user_home }} - Current user's home directory (cross-platform)
        try:
            user_home = Path.home()
            builtin_vars["user_home"] = str(user_home)
        except Exception as e:
            raise ExecutionError(
                f"Failed to get user home directory for {{ tt.user_home }}: {e}"
            )

        # {{ tt.user_name }} - Current username (with fallback)
        try:
            user_name = os.getlogin()
        except OSError:
            # Fallback to environment variables if os.getlogin() fails
            user_name = (
                os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
            )
        builtin_vars["user_name"] = user_name

        return builtin_vars

    def _collect_builtin_variables(
        self, task: Task, working_dir: Path, timestamp: datetime
    ) -> dict[str, str]:
        """
        Collect built-in variables for task execution.

        Args:
        task: Task being executed
        working_dir: Resolved working directory for the task
        timestamp: Timestamp when task started execution

        Returns:
        Dictionary mapping built-in variable names to their string values

        Raises:
        ExecutionError: If any built-in variable fails to resolve
        """
        # Get early builtin vars (those that don't depend on working_dir)
        builtin_vars = self._collect_early_builtin_variables(task, timestamp)

        # {{ tt.working_dir }} - Absolute path to task's effective working directory
        # This is added after working_dir is resolved to avoid circular dependency
        builtin_vars["working_dir"] = str(working_dir.resolve())

        return builtin_vars

    def _prepare_env_with_exports(
        self,
        exported_env_vars: dict[str, str] | None = None,
        call_chain: str | None = None,
    ) -> dict[str, str]:
        """
        Prepare environment with exported arguments and call chain.

        Args:
        exported_env_vars: Exported arguments to set as environment variables
        call_chain: TT_CALL_CHAIN value for recursion detection

        Returns:
        Environment dict with exported args and call chain merged

        Raises:
        ValueError: If an exported arg attempts to override a protected environment variable
        """
        env = os.environ.copy()
        if exported_env_vars:
            # Check for protected environment variable overrides
            for key in exported_env_vars:
                if key in self.PROTECTED_ENV_VARS:
                    raise ValueError(
                        f"Cannot override protected environment variable: {key}\n"
                        f"Protected variables are: {', '.join(sorted(self.PROTECTED_ENV_VARS))}"
                    )
            env.update(exported_env_vars)

        # Add call chain for recursion detection
        if call_chain is not None:
            env[self.TT_CALL_CHAIN_ENV_VAR] = call_chain

        return env

    def _try_load_config(
        self,
        config_path: Path,
        config_level: str,
        treat_permission_as_trace: bool = False,
    ) -> Runner | None:
        """
        Helper to load a config file with standardized error handling.

        Args:
            config_path: Path to the config file
            config_level: Description of config level (e.g., "machine", "user", "project")
            treat_permission_as_trace: If True, PermissionError logs at trace level instead of warn

        Returns:
            Runner if config exists and is valid, None otherwise

        Note:
            Relative paths in config files are stored as-is and resolved at task
            execution time. See parse_config_file() for details.
        """
        # Import here to avoid circular dependency
        from tasktree.config import parse_config_file

        try:
            if config_path.exists():
                runner = parse_config_file(config_path)
                if runner:
                    self.logger.debug(
                        f"Using runner from {config_level} config at '{config_path}' as session default runner"
                    )
                    return runner
            else:
                self.logger.trace(f"No {config_level} config found at '{config_path}'")
        except (ConfigError, OSError) as e:
            # PermissionError (subclass of OSError) may be expected for some configs
            # (e.g., machine-level on Unix) - log at trace level if requested
            # Other errors indicate real problems - log at warn level
            if treat_permission_as_trace and isinstance(e, PermissionError):
                self.logger.trace(f"Cannot read {config_level} config (permission denied): {e}")
            else:
                self.logger.warn(f"Failed to load {config_level} config: {e}")
        return None

    def get_session_default_runner(self, start_dir: Path = None) -> Runner:
        """
        Get the session default runner based on configuration hierarchy.

        Search (i.e. precedence) order (first encountered wins):
        1. Project-level config (checked here)
        2. User-level config (checked here)
        3. Machine-level config (checked here)
        4. Platform default (baseline)

        Args:
            start_dir: Directory to start searching for project config.
                      Defaults to current working directory.

        Returns:
            Runner: Session default runner configuration

        Note:
            Relative paths in config files (e.g., dockerfile paths) are resolved
            relative to project_root at task execution time. If a relative path
            cannot be resolved (e.g., dockerfile doesn't exist), the error will
            occur during task execution, not during config loading.

        """
        # Import here to avoid circular dependency
        from tasktree.config import (
            find_project_config,
            get_machine_config_path,
            get_user_config_path,
        )

        # Start with platform default
        platform_default = Runner(
            name="__platform_default__",
            interpreter=platform_default_interpreter(),
        )

        session_default = platform_default

        # Get project root for path resolution
        project_root = self.recipe.project_root

        # Check for machine-level config (higher precedence than platform default)
        machine_config_path = get_machine_config_path()
        machine_runner = self._try_load_config(
            machine_config_path, "machine", treat_permission_as_trace=True
        )
        if machine_runner:
            session_default = machine_runner

        # Check for user-level config (higher precedence than machine config)
        user_config_path = get_user_config_path()
        user_runner = self._try_load_config(user_config_path, "user")
        if user_runner:
            session_default = user_runner

        # Determine starting directory for project config
        if start_dir is None:
            start_dir = Path.cwd()

        # Check for project-level config (highest precedence)
        project_config_path = find_project_config(start_dir)
        if project_config_path:
            project_runner = self._try_load_config(
                project_config_path, "project"
            )
            if project_runner:
                session_default = project_runner

        if session_default == platform_default:
            self.logger.debug("Using platform default runner for session")

        return session_default

    def _get_effective_runner_name(self, task: Task) -> str:
        """
        Get the effective runner name for a task.

        Resolution order:
        1. Recipe's global_runner_override (from CLI --runner)
        2. Task's explicit run_in field (includes blanket runner if applied)
        3. Recipe's default_runner
        4. Session default runner name (from get_session_default_runner)

        Note: Pinned tasks (pin_runner=true) must have run_in specified.

        Args:
        task: Task to get runner name for

        Returns:
        Runner name (session default runner name if no other override)
        """
        # Validate pinned tasks have a runner specified
        if task.pin_runner and not task.run_in:
            raise ValueError(
                f"Task '{task.name}' has pin_runner=true but no run_in specified. "
                f"Pinned tasks must explicitly declare their runner."
            )

        # Check for global override first
        if self.recipe.global_runner_override:
            return self.recipe.global_runner_override

        # Use task's runner
        if task.run_in:
            return task.run_in

        # Use recipe default
        if self.recipe.default_runner:
            return self.recipe.default_runner

        # Return session default runner name
        return self.get_session_default_runner().name

    def _validate_runner_for_task(self, task: Task) -> None:
        """Raise ValueError if a shell runner for this task has docker-only fields set."""
        runner_name = self._get_effective_runner_name(task)
        if not runner_name:
            return
        runner = self.recipe.get_runner(runner_name)
        if runner is None or runner.dockerfile:
            return
        docker_only_fields = {
            "volumes": runner.volumes,
            "ports": runner.ports,
            "env_vars": runner.env_vars,
        }
        for field_name, value in docker_only_fields.items():
            if value:
                raise ValueError(
                    f"Runner '{runner_name}': '{field_name}' is only valid for Docker runners "
                    f"(runners with a 'dockerfile' field)"
                )
        if runner.run_as_root:
            raise ValueError(
                f"Runner '{runner_name}': 'run_as_root' is only valid for Docker runners "
                f"(runners with a 'dockerfile' field)"
            )
        if runner.args.build or runner.args.run:
            raise ValueError(
                f"Runner '{runner_name}': 'args' is only valid for Docker runners "
                f"(runners with a 'dockerfile' field)"
            )

    def _validate_runners_for_reachable_tasks(
        self, execution_order: list[tuple[str, dict]]
    ) -> None:
        """Validate all runners required by the reachable tasks before execution begins."""
        for name, _ in execution_order:
            task = self.recipe.tasks[name]
            self._validate_runner_for_task(task)

    def _resolve_interpreter(self, task: Task) -> Interpreter:
        """
        Resolve the Interpreter used to run a task's command.

        Resolution order (highest to lowest precedence):
        1. CLI --interpreter override (a name in the interpreters section)
        2. Task's explicit ``interpreter`` (a name in the interpreters section)
        3. The effective runner's ``interpreter``
        4. The session/platform default interpreter

        Both name-based overrides are validated to exist before execution (the
        CLI value in execute_dynamic_task, the task value at parse time).

        Args:
        task: Task being executed

        Returns:
        The Interpreter to invoke the task's temp script with
        """
        if self.recipe.global_interpreter_override:
            return self.recipe.interpreters[self.recipe.global_interpreter_override]

        if task.interpreter:
            return self.recipe.interpreters[task.interpreter]

        runner = self.recipe.get_runner(self._get_effective_runner_name(task))
        if runner is not None and runner.interpreter is not None:
            return runner.interpreter

        # A Docker runner with no interpreter defaults to sh (always present in a
        # container); host execution falls back to the session/platform default.
        if runner is not None and runner.dockerfile:
            return container_default_interpreter()

        return self.get_session_default_runner().interpreter or platform_default_interpreter()

    @staticmethod
    def _interpreter_identity(interpreter: Interpreter) -> str:
        """A stable string identity for hashing (cmd + ext + preamble)."""
        return f"{interpreter.cmd}\x00{interpreter.ext}\x00{interpreter.preamble}"

    def check_task_status(
        self,
        task: Task,
        args_dict: dict[str, Any],
        process_runner: ProcessRunner,
        force: bool = False,
    ) -> TaskStatus:
        """
        Check if a task needs to run.

        A task executes if ANY of these conditions are met:
        1. Force flag is set (--force)
        2. Task definition hash differs from cached state
        3. Runner definition has changed
        4. Any explicit inputs have newer mtime than last_run
        5. Any implicit inputs (from deps) have changed
        6. No cached state exists for this task+args combination
        7. Task has no inputs (always runs)
        8. Different arguments than any cached execution

        Args:
        task: Task to check
        args_dict: Arguments for this task execution
        process_runner: ProcessRunner instance for subprocess execution
        force: If True, ignore freshness and force execution

        Returns:
        TaskStatus indicating whether task will run and why
        """
        # If force flag is set, always run
        if force:
            self.logger.debug(f"Task '{task.name}' will run: force flag specified")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="forced",
            )

        # Compute hashes (include effective environment and dependencies)
        effective_env = self._get_effective_runner_name(task)
        task_hash = hash_task(
            task.cmd,
            task.outputs,
            task.working_dir,
            task.args,
            effective_env,
            task.deps,
            self._interpreter_identity(self._resolve_interpreter(task)),
        )
        self.logger.trace(f"Task hash for '{task.name}': {task_hash}")
        args_hash = hash_args(args_dict) if args_dict else None
        if args_hash:
            self.logger.trace(f"Args hash: {args_hash}")
        cache_key = make_cache_key(task_hash, args_hash)
        self.logger.trace(f"Cache key: {cache_key}")

        # Check if task has no inputs (always runs)
        # This check happens early to match original behavior
        all_inputs = self._get_all_inputs(task, args_dict)
        if not all_inputs:
            cached_state = self.state.get(cache_key)
            self.logger.debug(f"Task '{task.name}' will run: task has no inputs (always runs)")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="no_inputs",
                last_run=datetime.fromtimestamp(cached_state.last_run) if cached_state else None,
            )

        # Check cached state
        cached_state = self.state.get(cache_key)
        if cached_state is None:
            self.logger.trace(f"No cached state found for cache key: {cache_key}")
            self.logger.debug(f"Task '{task.name}' will run: no previous execution found")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="never_run",
            )

        self.logger.trace(f"Found cached state for '{task.name}' (last run: {datetime.fromtimestamp(cached_state.last_run).isoformat()})")

        env_changed = self._check_runner_changed(
            task, cached_state, effective_env, process_runner
        )
        if env_changed:
            self.logger.debug(f"Task '{task.name}' will run: runner definition changed")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="environment_changed",
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Check if inputs have changed
        changed_files = self._check_inputs_changed(
            task, cached_state, all_inputs, process_runner
        )
        if changed_files:
            files_list = ", ".join(changed_files)
            self.logger.debug(f"Task '{task.name}' will run: inputs changed: {files_list}")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="inputs_changed",
                changed_files=changed_files,
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Check if declared outputs are missing
        missing_outputs = self._check_outputs_missing(
            task, cached_state, process_runner
        )
        if missing_outputs:
            outputs_list = ", ".join(missing_outputs)
            self.logger.debug(f"Task '{task.name}' will run: outputs missing: {outputs_list}")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="outputs_missing",
                changed_files=missing_outputs,
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Inputs/outputs are fresh. For a containerised task, the probe above will
        # have (cache-aware) built the image; if its content fingerprint differs
        # from the stored one, the environment changed and the task must re-run.
        if self._image_fingerprint_changed(task, cached_state, process_runner):
            self.logger.debug(f"Task '{task.name}' will run: container image changed")
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="environment_changed",
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Task is fresh
        self.logger.debug(f"Task '{task.name}' is up-to-date, skipping")
        return TaskStatus(
            task_name=task.name,
            will_run=False,
            reason="fresh",
            last_run=datetime.fromtimestamp(cached_state.last_run),
        )

    @staticmethod
    def _get_task_output_type(
        user_inputted_value: TaskOutputTypes | None, task: Task
    ) -> TaskOutputTypes:
        if user_inputted_value is None:
            if task.task_output is not None:
                return task.task_output

            return TaskOutputTypes.ALL

        return user_inputted_value

    def execute_task(
        self,
        task_name: str,
        user_inputted_task_output_types: TaskOutputTypes | None,
        args_dict: dict[str, Any] | None = None,
        force: bool = False,
        only: bool = False,
    ) -> dict[str, TaskStatus]:
        """
        Execute a task and its dependencies.

        Args:
        task_name: Name of task to execute
        task_output_type: TaskOutputTypes enum value for controlling subprocess output
        args_dict: Arguments to pass to the task
        force: If True, ignore freshness and re-run all tasks
        only: If True, run only the specified task without dependencies (implies force=True)

        Returns:
        Dictionary of task names to their execution status

        Raises:
        ExecutionError: If task execution fails
        """
        if args_dict is None:
            args_dict = {}

        # When only=True, force execution (ignore freshness)
        if only:
            force = True

        # Resolve execution order
        if only:
            # Only execute the target task, skip dependencies
            execution_order = [(task_name, args_dict)]
            self.logger.debug(f"Skipping dependencies (--only mode)")
        else:
            # Execute task and all dependencies
            execution_order = resolve_execution_order(self.recipe, task_name, args_dict)
            task_names = [name for name, _ in execution_order]
            self.logger.debug(f"Execution order: {' -> '.join(task_names)}")

        # Validate runners for all reachable tasks before executing anything
        self._validate_runners_for_reachable_tasks(execution_order)

        # Resolve dependency output references in topological order
        # This substitutes {{ dep.*.outputs.* }} templates before execution
        resolve_dependency_output_references(self.recipe, execution_order)

        # Resolve self-references in topological order
        # This substitutes {{ self.inputs.* }} and {{ self.outputs.* }} templates
        resolve_self_references(self.recipe, execution_order)

        # Single phase: Check and execute incrementally
        statuses: dict[str, TaskStatus] = {}
        for name, task_args in execution_order:
            task = self.recipe.tasks[name]

            # Convert None to {} for internal use (None is used to distinguish simple deps in graph)
            args_dict_for_execution = task_args if task_args is not None else {}

            process_runner = self._process_runner_factory(
                self._get_task_output_type(user_inputted_task_output_types, task),
                self.logger,
            )

            # Check if task needs to run (based on CURRENT filesystem state)
            status = self.check_task_status(
                task, args_dict_for_execution, process_runner, force=force
            )

            # Use a key that includes args for status tracking
            # Only include regular (non-exported) args in status key for parameterized dependencies
            # For the root task (invoked from CLI), status key is always just the task name
            # For dependencies with parameterized invocations, include the regular args
            is_root_task = name == task_name
            if (
                not is_root_task
                and args_dict_for_execution
                and self._has_regular_args(task)
            ):
                import json

                # Filter to only include regular (non-exported) args
                regular_args = self._filter_regular_args(task, args_dict_for_execution)
                if regular_args:
                    args_str = json.dumps(
                        regular_args, sort_keys=True, separators=(",", ":")
                    )
                    status_key = f"{name}({args_str})"
                else:
                    status_key = name
            else:
                status_key = name
            statuses[status_key] = status

            # Execute immediately if needed
            if status.will_run:
                # Warn if re-running due to missing outputs
                if status.reason == "outputs_missing":
                    self.logger.log(
                        LogLevel.WARN,
                        f"Warning: Re-running task '{name}' because declared outputs are missing",
                    )

                self._run_task(task, args_dict_for_execution, process_runner)

        return statuses

    @staticmethod
    def _parse_call_chain(call_chain: str) -> list[tuple[str, str]]:
        """
        Parse TT_CALL_CHAIN environment variable into list of (cache_key, task_name) tuples.

        Args:
        call_chain: Comma-separated entries in 'cache_key:task_name' format

        Returns:
        List of (cache_key, task_name) tuples in the call chain (empty list if chain is empty)
        """
        if not call_chain.strip():
            return []

        entries = []
        for entry in call_chain.split(","):
            entry = entry.strip()
            if not entry:
                continue
            # Split on first ':' to separate cache_key from task_name
            parts = entry.split(":", 1)
            if len(parts) == 2:
                cache_key, task_name = parts
                entries.append((cache_key, task_name))
        return entries

    @staticmethod
    def _make_call_chain_entry(cache_key: str, task_name: str) -> str:
        """
        Create call chain entry in format 'cache_key:task_name'.

        Args:
            cache_key: Unique cache key for this task execution (hash of task + args)
            task_name: Human-readable task name for error messages

        Returns:
            Formatted call chain entry
        """
        return f"{cache_key}:{task_name}"

    @staticmethod
    def _resolve_container_path(host_path: Path, volumes: list[str]) -> Path:
        """
        Resolve the container path for a given host path based on volume mounts.

        Args:
            host_path: Host file system path
            volumes: List of volume mount specifications (e.g., ["./src:/app/src", ".:/workspace"])

        Returns:
            Container path if a matching volume mount is found, otherwise the host path
        """
        # Resolve host_path to absolute to handle relative paths like "."
        host_path = host_path.resolve()

        # Check each volume mount to see if it covers the host_path
        for volume in volumes:
            # Parse volume specification: "host:container[:mode]"
            parts = volume.split(":")
            if len(parts) < 2:
                continue

            mount_host = parts[0]
            mount_container = parts[1]

            # Resolve mount_host to absolute
            mount_host_path = Path(mount_host).resolve()

            # Check if host_path is within or equal to mount_host_path
            try:
                # Get the relative path from mount_host to host_path
                rel_path = host_path.relative_to(mount_host_path)
                # Return the corresponding container path
                if str(rel_path) == ".":
                    return Path(mount_container)
                else:
                    return Path(mount_container) / rel_path
            except ValueError:
                # host_path is not relative to mount_host_path, try next volume
                continue

        # No matching volume mount found, return host path
        return host_path

    def _validate_nested_docker_runner(
        self, task: Task, current_containerized_runner: str
    ) -> bool:
        """
        Validate runner compatibility when already inside a container.

        Args:
            task: Task to validate
            current_containerized_runner: Name of the current containerized runner

        Returns:
            bool: True if shell execution should be forced (compatible scenario)

        Raises:
            ExecutionError: If task requires incompatible Docker runner

        """
        task_runner_name = self._get_effective_runner_name(task)

        # Task specifies a runner - check if it's compatible
        if task_runner_name and task_runner_name != current_containerized_runner:
            task_runner = self.recipe.get_runner(task_runner_name)

            # REFINED REJECTION LOGIC:
            # Only reject if:
            # 1. Task has run_in specified (checked above via task_runner_name)
            # 2. The specified runner has a dockerfile field
            # 3. The dockerfile differs from current container's runner
            # 4. We're in the same project (cross-project invocations are allowed)
            if task_runner and task_runner.dockerfile:
                # Check if this is a cross-project invocation
                parent_project_root = os.environ.get("TT_PROJECT_ROOT", "").strip()
                current_project_root = str(self.recipe.project_root)

                # Allow Docker runner transition if we're in a different project
                if parent_project_root and parent_project_root != current_project_root:
                    # Different project - allow the Docker runner transition
                    return True

                raise ExecutionError(
                    f"Task '{task.name}' requires containerized runner '{task_runner_name}' "
                    f"but is currently executing inside runner '{current_containerized_runner}'. "
                    f"Nested Docker-in-Docker invocations across different containerized runners are not supported. "
                    f"Either remove the runner specification from '{task.name}', ensure it matches "
                    f"the parent task's runner, or use a shell-only runner."
                )

        # If we get here, either:
        # - Same containerized runner name → use it directly
        # - Different shell-only runner → allowed, use its shell/preamble
        # - No runner specified → use shell execution in current container
        return True

    def _run_task(
        self, task: Task, args_dict: dict[str, Any], process_runner: ProcessRunner
    ) -> None:
        """
        Execute a single task.

        Args:
        task: Task to execute
        args_dict: Arguments to substitute in command
        process_runner: ProcessRunner instance for subprocess execution

        Raises:
        ExecutionError: If task execution fails
        """
        # Capture timestamp at task start for consistency (in UTC)
        task_start_time = datetime.now(timezone.utc)

        # Check for recursion via TT_CALL_CHAIN
        current_chain = os.environ.get(self.TT_CALL_CHAIN_ENV_VAR, "")
        chain_list = self._parse_call_chain(current_chain)

        # Use fully-qualified task name (includes import prefix if any)
        task_fqn = task.name  # Already includes import prefix from parser

        # Generate cache key for this task execution (includes args hash)
        cache_key = self._cache_key(task, args_dict)

        # Check if this task execution (same task + args) is already in the call chain
        cache_keys_in_chain = [entry[0] for entry in chain_list]
        if cache_key in cache_keys_in_chain:
            # Recursion detected - build cycle path for error message
            cycle_start_idx = cache_keys_in_chain.index(cache_key)
            # Extract task names from tuples for display
            task_names_in_cycle = [entry[1] for entry in chain_list[cycle_start_idx:]]
            cycle_path = task_names_in_cycle + [task_fqn]
            cycle_str = " → ".join(cycle_path)

            raise ExecutionError(
                f"Recursion detected in task invocation chain:\n"
                f"{cycle_str}\n\n"
                f"Task '{task_fqn}' is already running in the call chain.\n"
                f"This would create an infinite loop."
            )

        # Add current task to chain for child processes
        current_entry = self._make_call_chain_entry(cache_key, task_fqn)
        # Build chain string from existing entries plus current
        chain_entries = [f"{k}:{n}" for k, n in chain_list] + [current_entry]
        updated_chain = ",".join(chain_entries) if chain_entries else current_entry

        # Check if we're already inside a containerized runner
        # Note: Only proceed if the variable is set AND non-empty
        # An empty string means we're not in a containerized environment
        current_containerized_runner = os.environ.get("TT_CONTAINERIZED_RUNNER", "").strip()
        force_shell_execution = False

        if current_containerized_runner:
            # We're inside a container - validate runner compatibility
            force_shell_execution = self._validate_nested_docker_runner(
                task, current_containerized_runner
            )

        # Record the state file's hash before execution
        # This allows us to skip re-reading if no nested tt calls modified it
        initial_state_hash = self.state.get_hash()

        # Parse task arguments to identify exported args
        # Note: args_dict already has defaults applied by CLI (cli.py:413-424)
        from tasktree.parser import parse_arg_spec

        exported_args = set()
        regular_args = {}
        exported_env_vars = {}

        for arg_spec in task.args:
            parsed = parse_arg_spec(arg_spec)
            if parsed.is_exported:
                exported_args.add(parsed.name)
                # Get value and convert to string for environment variable
                # Value should always be in args_dict (CLI applies defaults)
                if parsed.name in args_dict:
                    exported_env_vars[parsed.name] = str(args_dict[parsed.name])
            else:
                if parsed.name in args_dict:
                    regular_args[parsed.name] = args_dict[parsed.name]

        # Collect early built-in variables (those that don't depend on working_dir)
        # These can be used in the working_dir field itself
        early_builtin_vars = self._collect_early_builtin_variables(
            task, task_start_time
        )

        # Resolve working directory
        # Validate that working_dir doesn't contain {{ tt.working_dir }} (circular dependency)
        self._validate_no_working_dir_circular_ref(task.working_dir)
        working_dir_str = self._render_field(
            task.working_dir, early_builtin_vars, regular_args, exported_args, task.name
        )
        working_dir = self.recipe.project_root / working_dir_str

        # Collect all built-in variables (including tt.working_dir now that it's resolved)
        builtin_vars = self._collect_builtin_variables(
            task, working_dir, task_start_time
        )

        # Render built-in variables, arguments, and environment variables in command.
        # Variables (var.*), dependency outputs (dep.*) and self-references (self.*)
        # were already resolved in earlier phases, so only tt/arg/env remain here.
        cmd = self._render_field(
            task.cmd, builtin_vars, regular_args, exported_args, task.name
        )

        # Resolve interpreter early so the shebang check can compare against it.
        interpreter = self._resolve_interpreter(task)

        # Warn if the user wrote a shebang in cmd: it has no effect because the
        # interpreter is always invoked explicitly, not by running the script directly.
        self._warn_if_cmd_has_shebang(cmd, interpreter)

        # Check if task uses Docker environment
        env_name = self._get_effective_runner_name(task)
        env = None
        if env_name:
            env = self.recipe.get_runner(env_name)

        # Execute command
        self.logger.log(LogLevel.INFO, f"Running: {task.name}")

        # Route to Docker execution or regular execution
        if not force_shell_execution and env and env.dockerfile:
            # Docker execution path - launch container
            self._run_task_in_docker(
                task,
                env,
                cmd,
                working_dir,
                process_runner,
                exported_env_vars,
                updated_chain,
            )
        else:
            # Shell execution path - either local or inside an existing container.
            # The interpreter (and its preamble) is resolved the same way in both
            # cases; a nested-in-container task uses its runner's interpreter.
            self._run_command_as_script(
                cmd,
                working_dir,
                task.name,
                interpreter,
                process_runner,
                exported_env_vars,
                updated_chain,
            )

        # Reload state from disk to capture any updates from nested tt calls
        # Only reload if the state file contents have changed since we started
        current_state_hash = self.state.get_hash()
        if current_state_hash != initial_state_hash:
            self.state.load()

        # Update state
        self._update_state(task, args_dict, process_runner)

    def _warn_if_cmd_has_shebang(self, cmd: str, interpreter: Interpreter) -> None:
        """Warn if a shebang in the task cmd field will be ineffective.

        On Windows shebangs are ignored entirely. On other platforms the
        shebang has no effect because the interpreter is invoked explicitly;
        warn only when the shebang specifies a different interpreter than the
        one that will actually run the script (a silent mismatch is confusing).
        """
        stripped = cmd.lstrip()
        if not stripped.startswith("#!"):
            return

        shebang_line = stripped.split("\n")[0]

        if platform.system() == "Windows":
            self.logger.warn(
                "[yellow]Shebang detected in cmd. "
                "On Windows, shebangs are ignored entirely.[/yellow]"
            )
            return

        shebang_interpreter = _extract_shebang_interpreter(shebang_line)
        if shebang_interpreter and shebang_interpreter != interpreter.cmd:
            self.logger.warn(
                f"[yellow]Shebang in cmd specifies '{shebang_interpreter}' but the task will "
                f"run with '{interpreter.cmd}'. The shebang has no effect — set 'interpreter:' "
                f"to choose a non-default interpreter.[/yellow]"
            )

    def _run_command_as_script(
        self,
        cmd: str,
        working_dir: Path,
        task_name: str,
        interpreter: Interpreter,
        process_runner: ProcessRunner,
        exported_env_vars: dict[str, str] | None = None,
        call_chain: str | None = None,
    ) -> None:
        """
        Execute a command via temporary script file (unified execution path).

        This method handles both single-line and multi-line commands by writing
        them to a temporary script file and executing the script. This provides
        consistent behavior and applies the interpreter's preamble to all commands.

        The interpreter's invocation is prepended to the script path when
        invoking the subprocess, e.g. ["python"] + ["/tmp/script"] →
        ["python", "/tmp/script"], used verbatim on any platform.

        Args:
        cmd: Command string (single-line or multi-line)
        working_dir: Working directory
        task_name: Task name (for error messages)
        interpreter: Interpreter used to invoke the temp script
        process_runner: ProcessRunner instance to use for subprocess execution
        exported_env_vars: Exported arguments to set as environment variables
        call_chain: TT_CALL_CHAIN value for recursion detection

        Raises:
        ExecutionError: If command execution fails
        """
        # Prepare environment with exported args and call chain
        env = self._prepare_env_with_exports(exported_env_vars, call_chain)

        # Create temporary script using context manager. The interpreter is passed
        # explicitly in the subprocess call, so no shebang is needed. The script
        # extension is the interpreter's literal ext (empty = no extension).
        with TempScript(
            logger=self.logger,
            cmd=cmd,
            preamble=interpreter.preamble,
            interpreter=interpreter,
        ) as script_path:
            run_cmd = interpreter.invocation + [str(script_path)]

            # Execute script file
            try:
                # If streams support fileno, pass them directly (most efficient).
                # CliRunner uses StringIO which has fileno() but raises on call,
                # so capture and write manually in that case.
                if not (_supports_fileno(sys.stdout) and _supports_fileno(sys.stderr)):
                    # CliRunner path: capture and write manually
                    result = process_runner.run(
                        run_cmd,
                        cwd=working_dir,
                        check=True,
                        capture_output=True,
                        text=True,
                        env=env,
                    )
                    if result.stdout:
                        sys.stdout.write(result.stdout)
                    if result.stderr:
                        sys.stderr.write(result.stderr)
                else:
                    process_runner.run(
                        run_cmd,
                        cwd=working_dir,
                        check=True,
                        stdout=sys.stdout,
                        stderr=sys.stderr,
                        env=env,
                    )
            except FileNotFoundError as e:
                # Check if this is a containerized environment
                # Note: Only proceed if the variable is set AND non-empty
                current_containerized_runner = os.environ.get("TT_CONTAINERIZED_RUNNER", "").strip()
                if current_containerized_runner and ("tt" in cmd or "tasktree" in cmd):
                    raise ExecutionError(
                        f"Task '{task_name}' failed: Command not found. "
                        f"When running nested tasks inside Docker container '{current_containerized_runner}', "
                        f"the 'tt' binary must be installed in the container image. "
                        f"Add 'RUN pip install tasktree' to your Dockerfile, or ensure the tasktree package "
                        f"is available in your container's Python environment."
                    ) from e
                else:
                    raise ExecutionError(
                        f"Task '{task_name}' failed: Command not found. {e}"
                    ) from e
            except subprocess.CalledProcessError as e:
                raise ExecutionError(
                    f"Task '{task_name}' failed with exit code {e.returncode}"
                )

    def _substitute_builtin_in_runner(
        self, env: Runner, builtin_vars: dict[str, str]
    ) -> Runner:
        """
        Substitute builtin and environment variables in runner fields.

        Args:
        env: Runner to process
        builtin_vars: Built-in variable values

        Returns:
        New Runner with builtin and environment variables substituted

        Raises:
        ValueError: If builtin variable or environment variable is not defined
        """
        from dataclasses import replace

        # Substitute in volumes (builtin vars first, then env vars)
        substituted_volumes = (
            [
                self._substitute_env(self._substitute_builtin(vol, builtin_vars))
                for vol in env.volumes
            ]
            if env.volumes
            else []
        )

        # Substitute in env_vars values (builtin vars first, then env vars)
        substituted_env_vars = (
            {
                key: self._substitute_env(self._substitute_builtin(value, builtin_vars))
                for key, value in env.env_vars.items()
            }
            if env.env_vars
            else {}
        )

        # Substitute in ports (builtin vars first, then env vars)
        substituted_ports = (
            [
                self._substitute_env(self._substitute_builtin(port, builtin_vars))
                for port in env.ports
            ]
            if env.ports
            else []
        )

        # Substitute in working_dir (builtin vars first, then env vars)
        substituted_working_dir = (
            self._substitute_env(
                self._substitute_builtin(env.working_dir, builtin_vars)
            )
            if env.working_dir
            else ""
        )

        def subst(s: str) -> str:
            return self._substitute_env(self._substitute_builtin(s, builtin_vars))

        # Substitute in docker build args
        substituted_build_args = [subst(arg) for arg in env.args.build]

        # Substitute in docker run args
        substituted_run_args = [subst(arg) for arg in env.args.run]

        # Substitute in the interpreter (cmd and preamble)
        substituted_interpreter = None
        if env.interpreter is not None:
            substituted_interpreter = replace(
                env.interpreter,
                cmd=subst(env.interpreter.cmd),
                preamble=subst(env.interpreter.preamble) if env.interpreter.preamble else "",
            )

        # Substitute in dockerfile (builtin vars first, then env vars)
        substituted_dockerfile = subst(env.dockerfile) if env.dockerfile else ""

        # Substitute in context (builtin vars first, then env vars)
        substituted_context = subst(env.context) if env.context else ""

        # Create new environment with substituted values
        return replace(
            env,
            volumes=substituted_volumes,
            env_vars=substituted_env_vars,
            ports=substituted_ports,
            working_dir=substituted_working_dir,
            args=DockerArgs(build=substituted_build_args, run=substituted_run_args),
            interpreter=substituted_interpreter,
            dockerfile=substituted_dockerfile,
            context=substituted_context,
        )

    def _run_task_in_docker(
        self,
        task: Task,
        env: Any,
        cmd: str,
        working_dir: Path,
        process_runner: ProcessRunner,
        exported_env_vars: dict[str, str] | None = None,
        call_chain: str | None = None,
    ) -> None:
        """
        Execute task inside Docker container.

        Args:
        task: Task to execute
        env: Docker environment configuration
        cmd: Command to execute
        working_dir: Host working directory
        process_runner: ProcessRunner instance to use for subprocess execution
        exported_env_vars: Exported arguments to set as environment variables
        call_chain: TT_CALL_CHAIN value for recursion detection
        task_output: Control task subprocess output (all, out, err, on-err, none)

        Raises:
        ExecutionError: If Docker execution fails
        """
        # Get builtin variables for substitution in environment fields
        task_start_time = datetime.now(timezone.utc)
        builtin_vars = self._collect_builtin_variables(
            task, working_dir, task_start_time
        )

        # Substitute builtin variables in environment fields (volumes, env_vars, etc.)
        env = self._substitute_builtin_in_runner(env, builtin_vars)

        # Resolve container working directory (see _container_working_dir).
        container_working_dir = self._container_working_dir(task, env, working_dir)

        # Validate and merge exported args with env vars (exported args take precedence)
        docker_env_vars = env.env_vars.copy() if env.env_vars else {}

        # Add nested invocation support environment variables
        docker_env_vars["TT_CONTAINERIZED_RUNNER"] = env.name

        # Resolve container path for project root from volume mounts
        container_project_root = self._resolve_container_path(
            self.recipe.project_root, env.volumes or []
        )
        docker_env_vars["TT_PROJECT_ROOT"] = str(container_project_root)

        # Add call chain for recursion detection
        if call_chain:
            docker_env_vars[self.TT_CALL_CHAIN_ENV_VAR] = call_chain

        if exported_env_vars:
            # Check for protected environment variable overrides
            for key in exported_env_vars:
                if key in self.PROTECTED_ENV_VARS:
                    raise ValueError(
                        f"Cannot override protected environment variable: {key}\n"
                        f"Protected variables are: {', '.join(sorted(self.PROTECTED_ENV_VARS))}"
                    )
            docker_env_vars.update(exported_env_vars)

        # The state file lives in the project root, which is bind-mounted into the
        # container, so nested `tt` calls read/write the same .tasktree-state with no
        # special mount. Ensure it exists so the bind mount (the repo) already
        # contains it before the container starts.
        if not self.state.state_path.exists():
            self.state.state_path.touch()

        # Create modified environment with merged env vars using dataclass replace
        from dataclasses import replace

        modified_env = replace(env, env_vars=docker_env_vars)

        # Execute in container
        try:
            self.docker_manager.run_in_container(
                env=modified_env,
                cmd=cmd,
                working_dir=working_dir,
                container_working_dir=container_working_dir,
                process_runner=process_runner,
                interpreter=self._resolve_interpreter(task),
            )
        except docker_module.DockerError as e:
            raise ExecutionError(str(e)) from e

    @staticmethod
    def _validate_no_working_dir_circular_ref(text: str) -> None:
        """
        Validate that working_dir field does not contain {{ tt.working_dir }}.

        Using {{ tt.working_dir }} in the working_dir field creates a circular dependency.

        Args:
        text: The working_dir field value to validate

        Raises:
        ExecutionError: If {{ tt.working_dir }} placeholder is found
        """
        import re

        # Pattern to match {{ tt.working_dir }} specifically
        pattern = re.compile(r"\{\{\s*tt\s*\.\s*working_dir\s*}}")

        if pattern.search(text):
            raise ExecutionError(
                "Cannot use {{ tt.working_dir }} in the 'working_dir' field.\n\n"
                "This creates a circular dependency (working_dir cannot reference itself).\n"
                "Other built-in variables like {{ tt.task_name }} or {{ tt.timestamp }} are allowed."
            )

    @staticmethod
    def _render_field(
        text: str,
        builtin_vars: dict[str, str],
        regular_args: dict[str, Any],
        exported_args: set[str] | None,
        task_name: str,
    ) -> str:
        """
        Render execution-time placeholders (tt.*, arg.*, env.*) in a field.

        Variables (var.*), dependency outputs (dep.*) and self-references (self.*)
        are resolved in earlier phases, so the only namespaces that remain at
        execution time are built-ins, arguments and the environment.

        Args:
        text: Field text containing remaining {{ ... }} placeholders
        builtin_vars: Built-in variable values (the tt namespace)
        regular_args: Non-exported argument values (the arg namespace)
        exported_args: Exported argument names (referencing one is an error)
        task_name: Current task name, used in error messages

        Returns:
        The rendered field text

        Raises:
        ValueError: If a placeholder cannot be resolved or the template is malformed
        """
        from tasktree.rendering import render
        from tasktree.task_config import build_task_config

        config = build_task_config(
            args=regular_args,
            exported_args=exported_args,
            builtins=builtin_vars,
        )
        return render(text, config, task_name=task_name)

    @staticmethod
    def _substitute_builtin(text: str, builtin_vars: dict[str, str]) -> str:
        """
        Substitute {{ tt.name }} placeholders in text.

        Built-in variables are resolved at execution time.

        Args:
        text: Text with {{ tt.name }} placeholders
        builtin_vars: Built-in variable values

        Returns:
        Text with built-in variables substituted

        Raises:
        ValueError: If built-in variable is not defined
        """
        from tasktree.substitution import substitute_builtin_variables

        return substitute_builtin_variables(text, builtin_vars)

    @staticmethod
    def _substitute_args(
        cmd: str, args_dict: dict[str, Any], exported_args: set[str] | None = None
    ) -> str:
        """
        Substitute {{ arg.name }} placeholders in command string.

        Variables are already substituted at parse time by the parser.
        This only handles runtime argument substitution.

        Args:
        cmd: Command with {{ arg.name }} placeholders
        args_dict: Argument values to substitute (only regular args)
        exported_args: Set of argument names that are exported (not available for substitution)

        Returns:
        Command with arguments substituted

        Raises:
        ValueError: If an exported argument is used in template substitution
        """
        from tasktree.substitution import substitute_arguments

        return substitute_arguments(cmd, args_dict, exported_args)

    @staticmethod
    def _substitute_env(text: str) -> str:
        """
        Substitute {{ env.NAME }} placeholders in text.

        Environment variables are resolved at execution time from os.environ.

        Args:
        text: Text with {{ env.NAME }} placeholders

        Returns:
        Text with environment variables substituted

        Raises:
        ValueError: If environment variable is not set
        """
        from tasktree.substitution import substitute_environment

        return substitute_environment(text)

    def _get_all_inputs(self, task: Task, args_dict: dict[str, Any] | None = None) -> list[str]:
        """
        Get all inputs for a task (explicit + implicit from dependencies).

        Args:
        task: Task to get inputs for
        args_dict: Argument values for this task execution, used to render
                   {{ arg.* }} templates in dependency output paths

        Returns:
        List of input glob patterns
        """
        # Extract paths from inputs (handle both anonymous strings and named dicts)
        all_inputs = []
        for inp in task.inputs:
            if isinstance(inp, str):
                all_inputs.append(inp)
            elif isinstance(inp, dict):
                # Named input - extract the path value(s)
                all_inputs.extend(inp.values())

        implicit_inputs = get_implicit_inputs(self.recipe, task, args_dict)
        all_inputs.extend(implicit_inputs)
        return all_inputs

    # TODO: Understand why task isn't used
    def _check_runner_changed(
        self,
        task: Task,
        cached_state: TaskState,
        env_name: str,
        process_runner: ProcessRunner,
    ) -> bool:
        """
        Check if environment definition has changed since last run.

        For shell environments: checks YAML definition hash
        For Docker environments: checks YAML hash, build-context file mtimes,
        and base-image local digests (NOT the built image ID, which is
        non-deterministic under BuildKit).

        Args:
        task: Task to check
        cached_state: Cached state from previous run
        env_name: Effective runner name (from _get_effective_runner_name)
        process_runner: ProcessRunner instance for subprocess execution

        Returns:
        True if environment definition changed, False otherwise
        """
        # If using platform default (no environment), no definition to track
        if not env_name or env_name == "__platform_default__":
            return False

        # Get environment definition
        env = self.recipe.get_runner(env_name)
        if env is None:
            # Runner was deleted - treat as changed
            return True

        # Compute current environment hash (YAML definition)
        from tasktree.hasher import hash_runner_definition

        current_env_hash = hash_runner_definition(env)
        self.logger.trace(f"Runner '{env_name}' hash: {current_env_hash}")

        # Get cached runner hash
        marker_key = f"_runner_hash_{env_name}"
        cached_env_hash = cached_state.input_state.get(marker_key)

        # If no cached hash (old state file), treat as changed to establish baseline
        if cached_env_hash is None:
            self.logger.trace(f"No cached runner hash found for '{env_name}'")
            return True

        self.logger.trace(f"Cached runner hash for '{env_name}': {cached_env_hash}")

        # Check if the runner's recipe-level definition changed.
        if current_env_hash != cached_env_hash:
            self.logger.trace(f"Runner '{env_name}' hash changed (cached: {cached_env_hash}, current: {current_env_hash})")
            return True

        # Docker image *content* changes (Dockerfile edits, new base image) are
        # detected separately, after the input/output probe builds the image -- see
        # _image_fingerprint_changed. Tasktree no longer tracks Docker build inputs
        # host-side; Docker's own layer cache decides whether the image rebuilds.
        return False

    def _check_inputs_changed(
        self,
        task: Task,
        cached_state: TaskState,
        all_inputs: list[str],
        process_runner: ProcessRunner | None = None,
    ) -> list[str]:
        """
        Check if any input files have changed since last run.

        Args:
        task: Task to check
        cached_state: Cached state from previous run
        all_inputs: All input glob patterns
        process_runner: Used to build/run the container for in-container probing

        Returns:
        List of changed file paths
        """
        changed_files = []

        # Keys starting with '_' are special entries (runner hashes, image
        # fingerprints, etc.) and are not file paths — skip them.
        cached_files = [p for p in cached_state.input_state if not p.startswith("_")]

        # Resolve current matches plus the existence of previously-tracked files
        # in a single probe (so the container variant needs only one round-trip).
        probe = self._freshness_probe(task, process_runner)
        stat = probe.stat_patterns(all_inputs + cached_files)

        current: dict[str, float] = {}
        for pattern in all_inputs:
            current.update(stat.get(pattern, {}))
        self.logger.trace(f"Checking {len(current)} input file(s) for task '{task.name}'")

        for file_path, current_mtime in current.items():
            cached_mtime = cached_state.input_state.get(file_path)
            if cached_mtime is None:
                self.logger.trace(f"Input file '{file_path}' has no cached mtime, treating as changed (current mtime: {current_mtime})")
                changed_files.append(file_path)
            elif current_mtime > cached_mtime:
                self.logger.trace(f"Input file '{file_path}' has changed (cached mtime: {cached_mtime}, current mtime: {current_mtime})")
                changed_files.append(file_path)
            else:
                self.logger.trace(f"Input file '{file_path}' is unchanged (mtime: {current_mtime})")

        # Also detect files that were previously tracked as inputs but are now
        # deleted (no longer matched and no longer present on disk).
        for cached_path in cached_files:
            if cached_path not in current and not stat.get(cached_path):
                self.logger.trace(f"Previously-tracked input file '{cached_path}' has been deleted")
                changed_files.append(cached_path)

        return changed_files

    @staticmethod
    def _expand_output_paths(task: Task) -> list[str]:
        """
        Extract all output paths from task outputs (both named and anonymous).

        Args:
        task: Task with outputs to extract

        Returns:
        List of output path patterns (glob patterns as strings)
        """
        paths = []
        for output in task.outputs:
            if isinstance(output, str):
                # Anonymous output: just the path string
                paths.append(output)
            elif isinstance(output, dict):
                # Named output: extract the path value
                paths.extend(output.values())
        return paths

    def _check_outputs_missing(
        self,
        task: Task,
        cached_state: "TaskState | None" = None,
        process_runner: ProcessRunner | None = None,
    ) -> list[str]:
        """
        Check if any declared outputs are missing.

        Also checks whether any individual file that was part of a glob-matched
        output set on the previous run has since been deleted, even if other
        files in the set still exist.

        Args:
        task: Task to check
        cached_state: Previously saved state (used to detect deleted glob members)
        process_runner: Used to build/run the container for in-container probing

        Returns:
        List of output patterns or file paths that are missing
        """
        if not task.outputs:
            return []

        missing_patterns = []

        # Expand outputs to paths (handles both named and anonymous)
        output_paths = self._expand_output_paths(task)
        cached_files = (
            list(cached_state.output_state)
            if cached_state and cached_state.output_state
            else []
        )
        self.logger.trace(f"Checking {len(output_paths)} output pattern(s) for task '{task.name}'")

        # One probe resolves both pattern matches and the existence of
        # previously-tracked output files.
        probe = self._freshness_probe(task, process_runner)
        stat = probe.stat_patterns(output_paths + cached_files)

        for pattern in output_paths:
            matches = stat.get(pattern, {})
            if not matches:
                self.logger.trace(f"Output pattern '{pattern}' has no matches (missing)")
                missing_patterns.append(pattern)
            else:
                self.logger.trace(f"Output pattern '{pattern}' has {len(matches)} match(es): {list(matches)}")

        # Also detect individual files that were previously output but are now
        # deleted. This catches the case where a glob like "build/bin/*" previously
        # matched [exe1, exe2] but now only matches [exe2] — exe1 is missing even
        # though the pattern still has matches.
        for file_path in cached_files:
            if not stat.get(file_path):
                self.logger.trace(f"Previously-tracked output file '{file_path}' is now missing")
                missing_patterns.append(file_path)

        return missing_patterns

    def _container_working_dir(
        self, task: Task, env: Runner, host_working_dir: Path
    ) -> str | None:
        """
        Resolve the working directory inside the container.

        A runner-level working_dir is an explicit override (combined with any task
        working_dir). Otherwise we default to the host working directory translated
        to its container path: the identity mapping in the common same-path mount
        case, or the user's chosen container path when they have remapped the
        project root (e.g. ".:/workspace" -> "/workspace").
        """
        task_wd = "" if task.working_dir == "." else task.working_dir
        if env.working_dir:
            return docker_module.resolve_container_working_dir(env.working_dir, task_wd)
        return str(self._resolve_container_path(host_working_dir, env.volumes or []))

    def _freshness_probe(
        self, task: Task, process_runner: ProcessRunner | None
    ) -> FreshnessProbe:
        """
        Build the freshness probe used to resolve a task's input/output patterns.

        For a task that will launch its own container (a Docker runner, and we are
        not already executing inside a container), returns a RunnerProbe so the
        patterns are resolved in the container's filesystem view. Otherwise -- a
        shell runner, or a nested call already running inside the container where
        the local filesystem *is* the container -- returns a HostProbe rooted at
        the task's working directory.
        """
        env = self._docker_env_for_top_level_task(task)
        if env is not None:
            host_working_dir = self.recipe.project_root / task.working_dir
            container_dir = self._container_working_dir(task, env, host_working_dir)

            def run(argv: list[str]) -> str:
                return self.docker_manager.capture_in_container(
                    env, argv, process_runner
                )

            return RunnerProbe(container_dir or str(host_working_dir), run)

        return HostProbe(self.recipe.project_root / task.working_dir)

    def _docker_env_for_top_level_task(self, task: Task) -> Runner | None:
        """
        Return the Docker runner for a task that will launch its own container,
        or None.

        This is the case where freshness must be assessed (and the image
        fingerprinted) inside a fresh container: the task uses a Docker runner and
        we are not already running inside a container (a nested call in a matching
        container runs as a shell against the local filesystem instead).

        The returned runner has built-in variables substituted in its fields (e.g.
        ``{{ tt.project_root }}`` in volumes/working_dir), exactly as the execution
        path does, so the probe resolves the same mounts and paths the task uses.
        """
        already_in_container = bool(
            os.environ.get("TT_CONTAINERIZED_RUNNER", "").strip()
        )
        if already_in_container:
            return None
        env_name = self._get_effective_runner_name(task)
        env = self.recipe.get_runner(env_name) if env_name else None
        if env and env.dockerfile:
            working_dir = self.recipe.project_root / task.working_dir
            builtin_vars = self._collect_builtin_variables(
                task, working_dir, datetime.now(timezone.utc)
            )
            return self._substitute_builtin_in_runner(env, builtin_vars)
        return None

    def _image_fingerprint_changed(
        self,
        task: Task,
        cached_state: TaskState,
        process_runner: ProcessRunner,
    ) -> bool:
        """
        Return True if a top-level containerised task's built image content differs
        from the fingerprint stored at the last run (i.e. the environment changed).

        This is the final staleness gate: by the time it runs, inputs/outputs are
        otherwise fresh and the input/output probe has already (cache-aware) built
        the image, so re-inspecting it here is cheap.
        """
        env = self._docker_env_for_top_level_task(task)
        if env is None:
            return False

        env_name = self._get_effective_runner_name(task)
        cached_fp = cached_state.input_state.get(f"_runner_image_fp_{env_name}")
        if cached_fp is None:
            # No stored fingerprint (e.g. pre-existing state) — re-run to baseline.
            self.logger.trace(f"No cached image fingerprint for '{env_name}'")
            return True

        image_tag, _ = self.docker_manager.ensure_image_built(env, process_runner)
        current_fp = self.docker_manager.image_content_fingerprint(image_tag)
        if current_fp != cached_fp:
            self.logger.trace(f"Image content fingerprint changed for '{env_name}'")
            return True
        return False

    def _update_state(
        self,
        task: Task,
        args_dict: dict[str, Any],
        process_runner: ProcessRunner | None = None,
    ) -> None:
        """
        Update state after task execution.
        """
        cache_key = self._cache_key(task, args_dict)
        input_state = self._input_files_to_modified_times(task, args_dict, process_runner)

        env_name = self._get_effective_runner_name(task)
        if env_name:
            env = self.recipe.get_runner(env_name)
            if env:
                input_state[f"_runner_hash_{env_name}"] = hash_runner_definition(env)

        # For a top-level containerised task, record the built image's content
        # fingerprint so that a later environment change (Dockerfile edit, new
        # base image, etc.) forces a re-run even when inputs/outputs are unchanged.
        fingerprint = self._current_image_fingerprint(task, process_runner)
        if fingerprint is not None:
            input_state[f"_runner_image_fp_{env_name}"] = fingerprint

        output_state = self._output_files_to_modified_times(task, process_runner)
        new_state = TaskState(last_run=time.time(), input_state=input_state, output_state=output_state)
        self.state.set(cache_key, new_state)
        self.state.save()

    def _current_image_fingerprint(
        self, task: Task, process_runner: ProcessRunner | None
    ) -> str | None:
        """
        Build (cache-aware) and fingerprint the image for a top-level containerised
        task, or return None if the task does not launch its own container.
        """
        env = self._docker_env_for_top_level_task(task)
        if env is None:
            return None
        image_tag, _ = self.docker_manager.ensure_image_built(env, process_runner)
        return self.docker_manager.image_content_fingerprint(image_tag)

    def _cache_key(self, task: Task, args_dict: dict[str, Any]) -> str:
        """
        """
        effective_env = self._get_effective_runner_name(task)
        task_hash = hash_task(
            task.cmd,
            task.outputs,
            task.working_dir,
            task.args,
            effective_env,
            task.deps,
            self._interpreter_identity(self._resolve_interpreter(task)),
        )
        args_hash = hash_args(args_dict) if args_dict else None
        return make_cache_key(task_hash, args_hash)

    def _input_files_to_modified_times(
        self,
        task: Task,
        args_dict: dict[str, Any] | None = None,
        process_runner: ProcessRunner | None = None,
    ) -> dict[str, float]:
        """
        Record current mtimes of all files matched by the task's input patterns.
        """
        stat = self._freshness_probe(task, process_runner).stat_patterns(
            self._get_all_inputs(task, args_dict)
        )
        input_state: dict[str, float] = {}
        for matches in stat.values():
            input_state.update(matches)
        return input_state

    def _output_files_to_modified_times(
        self, task: Task, process_runner: ProcessRunner | None = None
    ) -> dict[str, float]:
        """
        Expand output patterns to actual files and record their mtimes.

        Used to detect when individual files within a glob-matched output set
        are later deleted, even if other files in the set still exist.
        """
        stat = self._freshness_probe(task, process_runner).stat_patterns(
            self._expand_output_paths(task)
        )
        output_state: dict[str, float] = {}
        for matches in stat.values():
            output_state.update(matches)
        return output_state

