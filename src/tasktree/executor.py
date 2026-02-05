"""Task execution and staleness detection."""

from __future__ import annotations

import io
import os
import platform
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tasktree import docker as docker_module
from tasktree.config import ConfigError
from tasktree.graph import (
    get_implicit_inputs,
    resolve_execution_order,
    resolve_dependency_output_references,
    resolve_self_references,
)
from tasktree.hasher import hash_args, hash_task, make_cache_key
from tasktree.logging import Logger, LogLevel
from tasktree.parser import Recipe, Task, Runner
from tasktree.process_runner import ProcessRunner, TaskOutputTypes
from tasktree.state import StateManager, TaskState
from tasktree.hasher import hash_runner_definition


@dataclass
class TaskStatus:
    """
    Status of a task for execution planning.
    @athena: a718e784981d
    """

    task_name: str
    will_run: bool
    reason: str  # "fresh", "inputs_changed", "definition_changed",
    # "never_run", "no_outputs", "outputs_missing", "forced", "environment_changed"
    changed_files: list[str] = field(default_factory=list)
    last_run: datetime | None = None


class ExecutionError(Exception):
    """
    Raised when task execution fails.
    @athena: f22d72903ee4
    """

    pass


class Executor:
    """
    Executes tasks with incremental execution logic.
    @athena: 779b12944194
    """

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
        @athena: d09e6a537c99
        """
        self.recipe = recipe
        self.state = state_manager
        self.logger = logger
        self._process_runner_factory = process_runner_factory
        self.docker_manager = docker_module.DockerManager(recipe.project_root)

    @staticmethod
    def _has_regular_args(task: Task) -> bool:
        """
        Check if a task has any regular (non-exported) arguments.

        Args:
        task: Task to check

        Returns:
        True if task has at least one regular (non-exported) argument, False otherwise
        @athena: c529cda63cce
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
        @athena: 1ae863406335
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
        @athena: a0c1316fd713
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
        @athena: 7f6203e8d617
        """
        # Get early builtin vars (those that don't depend on working_dir)
        builtin_vars = self._collect_early_builtin_variables(task, timestamp)

        # {{ tt.working_dir }} - Absolute path to task's effective working directory
        # This is added after working_dir is resolved to avoid circular dependency
        builtin_vars["working_dir"] = str(working_dir.resolve())

        return builtin_vars

    def _prepare_env_with_exports(
        self, exported_env_vars: dict[str, str] | None = None
    ) -> dict[str, str]:
        """
        Prepare environment with exported arguments.

        Args:
        exported_env_vars: Exported arguments to set as environment variables

        Returns:
        Environment dict with exported args merged

        Raises:
        ValueError: If an exported arg attempts to override a protected environment variable
        @athena: 5340be771194
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
        return env

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
        @athena: to-be-generated
        """
        # Import here to avoid circular dependency
        from tasktree.config import (
            find_project_config,
            get_machine_config_path,
            get_user_config_path,
            parse_config_file,
        )

        # Start with platform default
        is_windows = platform.system() == "Windows"
        if is_windows:
            platform_default = Runner(name="__platform_default__", shell="cmd", args=["/c"])
        else:
            platform_default = Runner(name="__platform_default__", shell="bash", args=["-c"])

        session_default = platform_default

        # Check for machine-level config (higher precedence than platform default)
        try:
            machine_config_path = get_machine_config_path()
            if machine_config_path.exists():
                machine_runner = parse_config_file(machine_config_path)
                if machine_runner:
                    self.logger.debug(
                        f"Using runner from machine config at '{machine_config_path}' as session default runner"
                    )
                    session_default = machine_runner
            else:
                self.logger.trace(f"No machine config found at '{machine_config_path}'")
        except PermissionError as e:
            # On Unix systems, site-level config may not be readable by all users
            # Skip it gracefully and continue to next level in hierarchy
            self.logger.trace(f"Cannot read machine config (permission denied): {e}")
        except (ConfigError, OSError, IOError) as e:
            # If config parsing fails, fall back to current session default
            self.logger.warn(f"Failed to load machine config: {e}")

        # Check for user-level config (higher precedence than machine config)
        try:
            user_config_path = get_user_config_path()
            if user_config_path.exists():
                user_runner = parse_config_file(user_config_path)
                if user_runner:
                    self.logger.debug(
                        f"Using runner from user config at '{user_config_path}' as session default runner"
                    )
                    session_default = user_runner
            else:
                self.logger.trace(f"No user config found at '{user_config_path}'")
        except (ConfigError, OSError, IOError) as e:
            # If config parsing fails, fall back to current session default
            self.logger.warn(f"Failed to load user config: {e}")

        # Determine starting directory for project config
        if start_dir is None:
            start_dir = Path.cwd()

        # Check for project-level config (highest precedence)
        try:
            project_config_path = find_project_config(start_dir)
            if project_config_path:
                project_runner = parse_config_file(project_config_path)
                if project_runner:
                    self.logger.debug(
                        f"Using runner from project config at '{project_config_path}' as session default runner"
                    )
                    session_default = project_runner
        except (ConfigError, OSError, IOError) as e:
            # If config parsing fails, fall back to current session default
            self.logger.warn(f"Failed to load project config: {e}")

        if session_default == platform_default:
            self.logger.debug("Using platform default runner for session")

        return session_default

    def _get_effective_runner_name(self, task: Task) -> str:
        """
        Get the effective runner name for a task.

        Resolution order:
        1. Recipe's global_env_override (from CLI --env)
        2. Task's explicit env field
        3. Recipe's default_env
        4. Session default runner name (from get_session_default_runner)

        Args:
        task: Task to get environment name for

        Returns:
        Runner name (session default runner name if no other override)
        @athena: e5bface8a3a2
        """
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

    def _resolve_runner(self, task: Task) -> tuple[str, str]:
        """
        Resolve which runner to use for a task.

        Resolution order:
        1. Recipe's global_env_override (from CLI --env)
        2. Task's explicit env field
        3. Recipe's default_env
        4. Platform default (bash on Unix, cmd on Windows)

        Args:
        task: Task to resolve environment for

        Returns:
        Tuple of (shell, preamble)
        @athena: 15cad76d7c80
        """
        # Check for global override first
        env_name = self.recipe.global_runner_override

        # If no global override, use task's runner
        if not env_name:
            env_name = task.run_in

        # If no explicit runner, try recipe default
        if not env_name and self.recipe.default_runner:
            env_name = self.recipe.default_runner

        # If we have a runner name, look it up
        if env_name:
            env = self.recipe.get_runner(env_name)
            if env:
                return env.shell, env.preamble
            # If runner not found, fall through to platform default

        # Use platform default
        default_runner = self.get_session_default_runner()
        return default_runner.shell, default_runner.preamble

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
        7. Task has no inputs AND no outputs (always runs)
        8. Different arguments than any cached execution

        Args:
        task: Task to check
        args_dict: Arguments for this task execution
        process_runner: ProcessRunner instance for subprocess execution
        force: If True, ignore freshness and force execution

        Returns:
        TaskStatus indicating whether task will run and why
        @athena: 03922de1bd23
        """
        # If force flag is set, always run
        if force:
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
        )
        args_hash = hash_args(args_dict) if args_dict else None
        cache_key = make_cache_key(task_hash, args_hash)

        # Check if task has no inputs and no outputs (always runs)
        all_inputs = self._get_all_inputs(task)
        if not all_inputs and not task.outputs:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="no_outputs",
            )

        # Check cached state
        cached_state = self.state.get(cache_key)
        if cached_state is None:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="never_run",
            )

        env_changed = self._check_runner_changed(
            task, cached_state, effective_env, process_runner
        )
        if env_changed:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="environment_changed",
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Check if inputs have changed
        changed_files = self._check_inputs_changed(task, cached_state, all_inputs)
        if changed_files:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="inputs_changed",
                changed_files=changed_files,
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Check if declared outputs are missing
        missing_outputs = self._check_outputs_missing(task)
        if missing_outputs:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="outputs_missing",
                changed_files=missing_outputs,
                last_run=datetime.fromtimestamp(cached_state.last_run),
            )

        # Task is fresh
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
        @athena: 4773fc590d9a
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
        else:
            # Execute task and all dependencies
            execution_order = resolve_execution_order(self.recipe, task_name, args_dict)

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
        @athena: b5abffeef10a
        """
        # Capture timestamp at task start for consistency (in UTC)
        task_start_time = datetime.now(timezone.utc)

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
        working_dir_str = self._substitute_builtin(task.working_dir, early_builtin_vars)
        working_dir_str = self._substitute_args(
            working_dir_str, regular_args, exported_args
        )
        working_dir_str = self._substitute_env(working_dir_str)
        working_dir = self.recipe.project_root / working_dir_str

        # Collect all built-in variables (including tt.working_dir now that it's resolved)
        builtin_vars = self._collect_builtin_variables(
            task, working_dir, task_start_time
        )

        # Substitute built-in variables, arguments, and environment variables in command
        cmd = self._substitute_builtin(task.cmd, builtin_vars)
        cmd = self._substitute_args(cmd, regular_args, exported_args)
        cmd = self._substitute_env(cmd)

        # Check if task uses Docker environment
        env_name = self._get_effective_runner_name(task)
        env = None
        if env_name:
            env = self.recipe.get_runner(env_name)

        # Execute command
        self.logger.log(LogLevel.INFO, f"Running: {task.name}")

        # Route to Docker execution or regular execution
        if env and env.dockerfile:
            # Docker execution path
            self._run_task_in_docker(
                task,
                env,
                cmd,
                working_dir,
                process_runner,
                exported_env_vars,
            )
        else:
            # Regular execution path - use unified script-based execution
            shell, preamble = self._resolve_runner(task)
            self._run_command_as_script(
                cmd,
                working_dir,
                task.name,
                shell,
                preamble,
                process_runner,
                exported_env_vars,
            )

        # Update state
        self._update_state(task, args_dict)

    def _run_command_as_script(
        self,
        cmd: str,
        working_dir: Path,
        task_name: str,
        shell: str,
        preamble: str,
        process_runner: ProcessRunner,
        exported_env_vars: dict[str, str] | None = None,
    ) -> None:
        """
        Execute a command via temporary script file (unified execution path).

        This method handles both single-line and multi-line commands by writing
        them to a temporary script file and executing the script. This provides
        consistent behavior and allows preamble to work with all commands.

        Args:
        cmd: Command string (single-line or multi-line)
        working_dir: Working directory
        task_name: Task name (for error messages)
        shell: Shell to use for script execution
        preamble: Preamble text to prepend to script
        process_runner: ProcessRunner instance to use for subprocess execution
        exported_env_vars: Exported arguments to set as environment variables

        Raises:
        ExecutionError: If command execution fails
        @athena: TBD
        @athena: 228cc00e7665
        """
        # Prepare environment with exported args
        env = self._prepare_env_with_exports(exported_env_vars)

        # Determine file extension based on platform
        is_windows = platform.system() == "Windows"
        script_ext = ".bat" if is_windows else ".sh"

        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=script_ext,
            delete=False,
        ) as script_file:
            script_path = script_file.name

            # On Unix/macOS, add shebang if not present
            if not is_windows and not cmd.startswith("#!"):
                # Use the configured shell in shebang
                shebang = f"#!/usr/bin/env {shell}\n"
                script_file.write(shebang)

            # Add preamble if provided
            if preamble:
                script_file.write(preamble)
                if not preamble.endswith("\n"):
                    script_file.write("\n")

            # Write command to file
            script_file.write(cmd)
            script_file.flush()

        try:
            # Make executable on Unix/macOS
            if not is_windows:
                os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC)

            # Execute script file
            try:
                # Check if stdout/stderr support fileno() (real file descriptors)
                # CliRunner uses StringIO which has fileno() method but raises when called
                def supports_fileno(stream):
                    """Check if a stream has a working fileno() method."""
                    try:
                        stream.fileno()
                        return True
                    except (AttributeError, OSError, io.UnsupportedOperation):
                        return False

                # Determine output targets based on task_output mode
                # For "all" mode: show everything
                # Future modes: use subprocess.DEVNULL for suppression
                should_suppress = False  # Will be: self.task_output == "none", etc.

                if should_suppress:
                    stdout_target = subprocess.DEVNULL
                    stderr_target = subprocess.DEVNULL
                else:
                    stdout_target = sys.stdout
                    stderr_target = sys.stderr

                # If streams support fileno, pass target streams directly (most efficient)
                # Otherwise capture and manually write (CliRunner compatibility)
                if not should_suppress and not (
                    supports_fileno(sys.stdout) and supports_fileno(sys.stderr)
                ):
                    # CliRunner path: capture and write manually
                    result = process_runner.run(
                        [script_path],
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
                    # Normal execution path: use target streams (including DEVNULL when suppressing)
                    process_runner.run(
                        [script_path],
                        cwd=working_dir,
                        check=True,
                        stdout=stdout_target,
                        stderr=stderr_target,
                        env=env,
                    )
            except subprocess.CalledProcessError as e:
                raise ExecutionError(
                    f"Task '{task_name}' failed with exit code {e.returncode}"
                )
        finally:
            # Clean up temporary file
            try:
                os.unlink(script_path)
            except OSError:
                pass  # Ignore cleanup errors

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
        @athena: eba6e3d62062
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

        # Substitute in build args (for Docker environments, args is a dict)
        # Apply builtin vars first, then env vars
        if isinstance(env.args, dict):
            substituted_args = {
                key: self._substitute_env(
                    self._substitute_builtin(str(value), builtin_vars)
                )
                for key, value in env.args.items()
            }
        else:
            substituted_args = env.args

        # Substitute in extra_args (builtin vars first, then env vars)
        substituted_extra_args = (
            [
                self._substitute_env(self._substitute_builtin(arg, builtin_vars))
                for arg in env.extra_args
            ]
            if env.extra_args
            else []
        )

        # Substitute in preamble (builtin vars first, then env vars)
        substituted_preamble = (
            self._substitute_env(self._substitute_builtin(env.preamble, builtin_vars))
            if env.preamble
            else ""
        )

        # Substitute in shell (builtin vars first, then env vars)
        substituted_shell = (
            self._substitute_env(self._substitute_builtin(env.shell, builtin_vars))
            if env.shell
            else ""
        )

        # Substitute in dockerfile (builtin vars first, then env vars)
        substituted_dockerfile = (
            self._substitute_env(self._substitute_builtin(env.dockerfile, builtin_vars))
            if env.dockerfile
            else ""
        )

        # Substitute in context (builtin vars first, then env vars)
        substituted_context = (
            self._substitute_env(self._substitute_builtin(env.context, builtin_vars))
            if env.context
            else ""
        )

        # Create new environment with substituted values
        return replace(
            env,
            volumes=substituted_volumes,
            env_vars=substituted_env_vars,
            ports=substituted_ports,
            working_dir=substituted_working_dir,
            args=substituted_args,
            extra_args=substituted_extra_args,
            preamble=substituted_preamble,
            shell=substituted_shell,
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
        task_output: Control task subprocess output (all, out, err, on-err, none)

        Raises:
        ExecutionError: If Docker execution fails
        @athena: 61725a57e304
        """
        # Get builtin variables for substitution in environment fields
        task_start_time = datetime.now(timezone.utc)
        builtin_vars = self._collect_builtin_variables(
            task, working_dir, task_start_time
        )

        # Substitute builtin variables in environment fields (volumes, env_vars, etc.)
        env = self._substitute_builtin_in_runner(env, builtin_vars)

        # Resolve container working directory
        # Treat "." as empty for Docker - it's the default but we want None
        # when neither env nor task explicitly sets working_dir, so Docker uses Dockerfile WORKDIR
        task_wd = "" if task.working_dir == "." else task.working_dir
        container_working_dir = docker_module.resolve_container_working_dir(
            env.working_dir, task_wd
        )

        # Validate and merge exported args with env vars (exported args take precedence)
        docker_env_vars = env.env_vars.copy() if env.env_vars else {}
        if exported_env_vars:
            # Check for protected environment variable overrides
            for key in exported_env_vars:
                if key in self.PROTECTED_ENV_VARS:
                    raise ValueError(
                        f"Cannot override protected environment variable: {key}\n"
                        f"Protected variables are: {', '.join(sorted(self.PROTECTED_ENV_VARS))}"
                    )
            docker_env_vars.update(exported_env_vars)

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
        @athena: 82822f02716a
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
        @athena: fe47afe87b52
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
        @athena: 9a931179f270
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
        @athena: 1bbe24759451
        """
        from tasktree.substitution import substitute_environment

        return substitute_environment(text)

    def _get_all_inputs(self, task: Task) -> list[str]:
        """
        Get all inputs for a task (explicit + implicit from dependencies).

        Args:
        task: Task to get inputs for

        Returns:
        List of input glob patterns
        @athena: ca7ed7a6682f
        """
        # Extract paths from inputs (handle both anonymous strings and named dicts)
        all_inputs = []
        for inp in task.inputs:
            if isinstance(inp, str):
                all_inputs.append(inp)
            elif isinstance(inp, dict):
                # Named input - extract the path value(s)
                all_inputs.extend(inp.values())

        implicit_inputs = get_implicit_inputs(self.recipe, task)
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
        For Docker environments: checks YAML hash AND Docker image ID

        Args:
        task: Task to check
        cached_state: Cached state from previous run
        env_name: Effective runner name (from _get_effective_runner_name)
        process_runner: ProcessRunner instance for subprocess execution

        Returns:
        True if environment definition changed, False otherwise
        @athena: e206e104150a
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

        # Get cached runner hash
        marker_key = f"_runner_hash_{env_name}"
        cached_env_hash = cached_state.input_state.get(marker_key)

        # If no cached hash (old state file), treat as changed to establish baseline
        if cached_env_hash is None:
            return True

        # Check if YAML definition changed
        if current_env_hash != cached_env_hash:
            return True  # YAML changed, no need to check image

        # For Docker environments, also check if image ID changed
        if env.dockerfile:
            return self._check_docker_image_changed(
                env, cached_state, env_name, process_runner
            )

        # Shell environment with unchanged hash
        return False

    def _check_docker_image_changed(
        self,
        env: Runner,
        cached_state: TaskState,
        env_name: str,
        process_runner: ProcessRunner,
    ) -> bool:
        """
        Check if Docker image ID has changed.

        Builds the image and compares the resulting image ID with the cached ID.
        This detects changes from unpinned base images, network-dependent builds, etc.

        Args:
        env: Docker runner definition
        cached_state: Cached state from previous run
        env_name: Runner name
        process_runner: ProcessRunner instance for subprocess execution

        Returns:
        True if image ID changed, False otherwise
        @athena: bc954288e4ad
        """
        # Build/ensure image is built and get its ID
        try:
            image_tag, current_image_id = self.docker_manager.ensure_image_built(
                env, process_runner
            )
        except Exception:
            # If we can't build, treat as changed (will fail later with better error)
            return True

        # Get cached image ID
        image_id_key = f"_docker_image_id_{env_name}"
        cached_image_id = cached_state.input_state.get(image_id_key)

        # If no cached ID (first run or old state), treat as changed
        if cached_image_id is None:
            return True

        # Compare image IDs
        return current_image_id != cached_image_id

    def _check_inputs_changed(
        self, task: Task, cached_state: TaskState, all_inputs: list[str]
    ) -> list[str]:
        """
        Check if any input files have changed since last run.

        Handles both regular file inputs and Docker-specific inputs:
        - Regular files: checked via mtime
        - Docker context: checked via directory walk with early exit
        - Dockerfile digests: checked via parsing and comparison

        Args:
        task: Task to check
        cached_state: Cached state from previous run
        all_inputs: All input glob patterns

        Returns:
        List of changed file paths
        @athena: 15b13fd181bf
        """
        changed_files = []

        # Expand glob patterns
        input_files = self._expand_globs(all_inputs, task.working_dir)

        # Check if task uses Docker environment
        env_name = self._get_effective_runner_name(task)
        docker_env = None
        if env_name:
            docker_env = self.recipe.get_runner(env_name)
            if docker_env and not docker_env.dockerfile:
                docker_env = None  # Not a Docker environment

        for file_path in input_files:
            # Handle Docker context directory check
            if file_path.startswith("_docker_context_"):
                if docker_env:
                    context_name = file_path.replace("_docker_context_", "")
                    context_path = self.recipe.project_root / context_name
                    dockerignore_path = context_path / ".dockerignore"

                    # Get last context check time
                    cached_context_time = cached_state.input_state.get(
                        f"_context_{context_name}"
                    )
                    if cached_context_time is None:
                        # Never checked before - consider changed
                        changed_files.append(f"Docker context: {context_name}")
                        continue

                    # Check if context changed (with early exit optimization)
                    if docker_module.context_changed_since(
                        context_path, dockerignore_path, cached_context_time
                    ):
                        changed_files.append(f"Docker context: {context_name}")
                continue

            # Handle Docker Dockerfile digest check
            if file_path.startswith("_docker_dockerfile_"):
                if docker_env:
                    dockerfile_name = file_path.replace("_docker_dockerfile_", "")
                    dockerfile_path = self.recipe.project_root / dockerfile_name

                    try:
                        dockerfile_content = dockerfile_path.read_text()
                        current_digests = set(
                            docker_module.parse_base_image_digests(dockerfile_content)
                        )

                        # Get cached digests
                        cached_digests = set()
                        for key in cached_state.input_state:
                            if key.startswith("_digest_"):
                                digest = key.replace("_digest_", "")
                                cached_digests.add(digest)

                        # Check if digests changed
                        if current_digests != cached_digests:
                            changed_files.append(
                                f"Docker base image digests in {dockerfile_name}"
                            )
                    except (OSError, IOError):
                        # Can't read Dockerfile - consider changed
                        changed_files.append(f"Dockerfile: {dockerfile_name}")
                continue

            # Regular file check
            file_path_obj = self.recipe.project_root / task.working_dir / file_path
            if not file_path_obj.exists():
                continue

            current_mtime = file_path_obj.stat().st_mtime

            # Check if file is in cached state
            cached_mtime = cached_state.input_state.get(file_path)
            if cached_mtime is None or current_mtime > cached_mtime:
                changed_files.append(file_path)

        return changed_files

    @staticmethod
    def _expand_output_paths(task: Task) -> list[str]:
        """
        Extract all output paths from task outputs (both named and anonymous).

        Args:
        task: Task with outputs to extract

        Returns:
        List of output path patterns (glob patterns as strings)
        @athena: 21da23ad5dcf
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

    def _check_outputs_missing(self, task: Task) -> list[str]:
        """
        Check if any declared outputs are missing.

        Args:
        task: Task to check

        Returns:
        List of output patterns that have no matching files
        @athena: 9ceac49b4e68
        """
        if not task.outputs:
            return []

        missing_patterns = []
        base_path = self.recipe.project_root / task.working_dir

        # Expand outputs to paths (handles both named and anonymous)
        output_paths = self._expand_output_paths(task)

        for pattern in output_paths:
            # Check if pattern has any matches
            matches = list(base_path.glob(pattern))
            if not matches:
                missing_patterns.append(pattern)

        return missing_patterns

    def _expand_globs(self, patterns: list[str], working_dir: str) -> list[str]:
        """
        Expand glob patterns to actual file paths.

        Args:
        patterns: List of glob patterns
        working_dir: Working directory to resolve patterns from

        Returns:
        List of file paths (relative to working_dir)
        @athena: 5ba093866558
        """
        files = []
        base_path = self.recipe.project_root / working_dir

        for pattern in patterns:
            # Use pathlib's glob
            matches = base_path.glob(pattern)
            for match in matches:
                if match.is_file():
                    # Make relative to working_dir
                    rel_path = match.relative_to(base_path)
                    files.append(str(rel_path))

        return files

    def _update_state(self, task: Task, args_dict: dict[str, Any]) -> None:
        """
        Update state after task execution.
        @athena: f4d3efdaac7c
        """
        cache_key = self._cache_key(task, args_dict)
        input_state = self._input_files_to_modified_times(task)

        env_name = self._get_effective_runner_name(task)
        if env_name:
            env = self.recipe.get_runner(env_name)
            if env:
                input_state[f"_runner_hash_{env_name}"] = hash_runner_definition(env)
                if env.dockerfile:
                    input_state |= self._docker_inputs_to_modified_times(env_name, env)

        new_state = TaskState(last_run=time.time(), input_state=input_state)
        self.state.set(cache_key, new_state)
        self.state.save()

    def _cache_key(self, task: Task, args_dict: dict[str, Any]) -> str:
        """
        @athena: d20ce4090741
        """
        effective_env = self._get_effective_runner_name(task)
        task_hash = hash_task(
            task.cmd,
            task.outputs,
            task.working_dir,
            task.args,
            effective_env,
            task.deps,
        )
        args_hash = hash_args(args_dict) if args_dict else None
        return make_cache_key(task_hash, args_hash)

    def _input_files_to_modified_times(self, task: Task) -> dict[str, float]:
        """
        @athena: 7e5ba779a41f
        """
        input_files = self._expand_globs(self._get_all_inputs(task), task.working_dir)

        input_state = {}
        for file_path in input_files:
            # Skip Docker special markers (handled separately)
            if file_path.startswith("_docker_"):
                continue

            file_path_obj = self.recipe.project_root / task.working_dir / file_path
            if file_path_obj.exists():
                input_state[file_path] = file_path_obj.stat().st_mtime

        return input_state

    def _docker_inputs_to_modified_times(
        self, env_name: str, env: Runner
    ) -> dict[str, float]:
        """
        @athena: bfe53b0d56cd
        """
        input_state = dict()
        # Record Dockerfile mtime
        dockerfile_path = self.recipe.project_root / env.dockerfile
        if dockerfile_path.exists():
            input_state[env.dockerfile] = dockerfile_path.stat().st_mtime

        # Record .dockerignore mtime if exists
        context_path = self.recipe.project_root / env.context
        dockerignore_path = context_path / ".dockerignore"
        if dockerignore_path.exists():
            relative_dockerignore = str(
                dockerignore_path.relative_to(self.recipe.project_root)
            )
            input_state[relative_dockerignore] = dockerignore_path.stat().st_mtime

        # Record context check timestamp
        input_state[f"_context_{env.context}"] = time.time()

        # Parse and record base image digests from Dockerfile
        try:
            dockerfile_content = dockerfile_path.read_text()
            digests = docker_module.parse_base_image_digests(dockerfile_content)
            for digest in digests:
                # Store digest with Dockerfile's mtime
                input_state[f"_digest_{digest}"] = dockerfile_path.stat().st_mtime
        except (OSError, IOError):
            # If we can't read Dockerfile, skip digest tracking
            pass

        # For Docker environments, also store the image ID
        # Image was already built during check phase or task execution
        if env_name in self.docker_manager._built_images:
            image_tag, image_id = self.docker_manager._built_images[env_name]
            input_state[f"_docker_image_id_{env_name}"] = image_id

        return input_state
