"""Task execution and staleness detection."""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tasktree.graph import get_implicit_inputs, resolve_execution_order
from tasktree.hasher import hash_args, hash_task, make_cache_key
from tasktree.parser import Recipe, Task
from tasktree.state import StateManager, TaskState


@dataclass
class TaskStatus:
    """Status of a task for execution planning."""

    task_name: str
    will_run: bool
    reason: str  # "fresh", "inputs_changed", "definition_changed",
    # "never_run", "dependency_triggered", "no_outputs"
    changed_files: list[str] = field(default_factory=list)
    last_run: datetime | None = None


class ExecutionError(Exception):
    """Raised when task execution fails."""

    pass


class Executor:
    """Executes tasks with incremental execution logic."""

    def __init__(self, recipe: Recipe, state_manager: StateManager):
        """Initialize executor.

        Args:
            recipe: Parsed recipe containing all tasks
            state_manager: State manager for tracking task execution
        """
        self.recipe = recipe
        self.state = state_manager

    def _get_platform_default_environment(self) -> tuple[str, list[str]]:
        """Get default shell and args for current platform.

        Returns:
            Tuple of (shell, args) for platform default
        """
        is_windows = platform.system() == "Windows"
        if is_windows:
            return ("cmd", ["/c"])
        else:
            return ("bash", ["-c"])

    def _get_effective_env_name(self, task: Task) -> str:
        """Get the effective environment name for a task.

        Resolution order:
        1. Recipe's global_env_override (from CLI --env)
        2. Task's explicit env field
        3. Recipe's default_env
        4. Empty string (for platform default)

        Args:
            task: Task to get environment name for

        Returns:
            Environment name (empty string if using platform default)
        """
        # Check for global override first
        if self.recipe.global_env_override:
            return self.recipe.global_env_override

        # Use task's env
        if task.env:
            return task.env

        # Use recipe default
        if self.recipe.default_env:
            return self.recipe.default_env

        # Platform default (no env name)
        return ""

    def _resolve_environment(self, task: Task) -> tuple[str, list[str], str]:
        """Resolve which environment to use for a task.

        Resolution order:
        1. Recipe's global_env_override (from CLI --env)
        2. Task's explicit env field
        3. Recipe's default_env
        4. Platform default (bash on Unix, cmd on Windows)

        Args:
            task: Task to resolve environment for

        Returns:
            Tuple of (shell, args, preamble)
        """
        # Check for global override first
        env_name = self.recipe.global_env_override

        # If no global override, use task's env
        if not env_name:
            env_name = task.env

        # If no explicit env, try recipe default
        if not env_name and self.recipe.default_env:
            env_name = self.recipe.default_env

        # If we have an env name, look it up
        if env_name:
            env = self.recipe.get_environment(env_name)
            if env:
                return (env.shell, env.args, env.preamble)
            # If env not found, fall through to platform default

        # Use platform default
        shell, args = self._get_platform_default_environment()
        return (shell, args, "")

    def check_task_status(
        self,
        task: Task,
        args_dict: dict[str, Any],
        dep_statuses: dict[str, TaskStatus],
        force: bool = False,
    ) -> TaskStatus:
        """Check if a task needs to run.

        A task executes if ANY of these conditions are met:
        1. Force flag is set (--force)
        2. Task definition hash differs from cached state
        3. Any explicit inputs have newer mtime than last_run
        4. Any implicit inputs (from deps) have changed
        5. No cached state exists for this task+args combination
        6. Task has no inputs AND no outputs (always runs)
        7. Different arguments than any cached execution

        Args:
            task: Task to check
            args_dict: Arguments for this task execution
            dep_statuses: Status of dependencies
            force: If True, ignore freshness and force execution

        Returns:
            TaskStatus indicating whether task will run and why
        """
        # If force flag is set, always run
        if force:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="forced",
            )

        # Compute hashes (include effective environment)
        effective_env = self._get_effective_env_name(task)
        task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, effective_env)
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

        # Check if any dependency triggered
        if any(status.will_run for status in dep_statuses.values()):
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="dependency_triggered",
            )

        # Check cached state
        cached_state = self.state.get(cache_key)
        if cached_state is None:
            return TaskStatus(
                task_name=task.name,
                will_run=True,
                reason="never_run",
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

    def execute_task(
        self,
        task_name: str,
        args_dict: dict[str, Any] | None = None,
        force: bool = False,
        only: bool = False,
    ) -> dict[str, TaskStatus]:
        """Execute a task and its dependencies.

        Args:
            task_name: Name of task to execute
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
            execution_order = [task_name]
        else:
            # Execute task and all dependencies
            execution_order = resolve_execution_order(self.recipe, task_name)

        # Check status of all tasks
        statuses: dict[str, TaskStatus] = {}
        for name in execution_order:
            task = self.recipe.tasks[name]

            # Get status of dependencies
            dep_statuses = {dep: statuses[dep] for dep in task.deps if dep in statuses}

            # Determine task-specific args (only for target task)
            task_args = args_dict if name == task_name else {}

            status = self.check_task_status(task, task_args, dep_statuses, force=force)
            statuses[name] = status

        # Execute tasks that need to run
        for name in execution_order:
            status = statuses[name]
            if status.will_run:
                # Warn if re-running due to missing outputs
                if status.reason == "outputs_missing":
                    import sys
                    print(
                        f"Warning: Re-running task '{name}' because declared outputs are missing",
                        file=sys.stderr,
                    )

                task = self.recipe.tasks[name]
                task_args = args_dict if name == task_name else {}
                self._run_task(task, task_args)

        return statuses

    def _run_task(self, task: Task, args_dict: dict[str, Any]) -> None:
        """Execute a single task.

        Args:
            task: Task to execute
            args_dict: Arguments to substitute in command

        Raises:
            ExecutionError: If task execution fails
        """
        # Substitute arguments in command
        cmd = self._substitute_args(task.cmd, args_dict)

        # Determine working directory
        working_dir = self.recipe.project_root / task.working_dir

        # Resolve environment for this task
        shell, shell_args, preamble = self._resolve_environment(task)

        # Execute command
        print(f"Running: {task.name}")

        # Detect multi-line commands
        if "\n" in cmd:
            self._run_multiline_command(cmd, working_dir, task.name, shell, preamble)
        else:
            self._run_single_line_command(cmd, working_dir, task.name, shell, shell_args)

        # Update state
        self._update_state(task, args_dict)

    def _run_single_line_command(
        self, cmd: str, working_dir: Path, task_name: str, shell: str, shell_args: list[str]
    ) -> None:
        """Execute a single-line command via shell.

        Args:
            cmd: Command string
            working_dir: Working directory
            task_name: Task name (for error messages)
            shell: Shell executable to use
            shell_args: Arguments to pass to shell

        Raises:
            ExecutionError: If command execution fails
        """
        try:
            # Build command: shell + args + cmd
            full_cmd = [shell] + shell_args + [cmd]
            subprocess.run(
                full_cmd,
                cwd=working_dir,
                check=True,
                capture_output=False,
            )
        except subprocess.CalledProcessError as e:
            raise ExecutionError(
                f"Task '{task_name}' failed with exit code {e.returncode}"
            )

    def _run_multiline_command(
        self, cmd: str, working_dir: Path, task_name: str, shell: str, preamble: str
    ) -> None:
        """Execute a multi-line command via temporary script file.

        Args:
            cmd: Multi-line command string
            working_dir: Working directory
            task_name: Task name (for error messages)
            shell: Shell to use for script execution
            preamble: Preamble text to prepend to script

        Raises:
            ExecutionError: If command execution fails
        """
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
                subprocess.run(
                    [script_path],
                    cwd=working_dir,
                    check=True,
                    capture_output=False,
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

    def _substitute_args(self, cmd: str, args_dict: dict[str, Any]) -> str:
        """Substitute arguments in command string.

        Args:
            cmd: Command template with {{arg}} placeholders
            args_dict: Arguments to substitute

        Returns:
            Command with arguments substituted
        """
        result = cmd
        for key, value in args_dict.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))
        return result

    def _get_all_inputs(self, task: Task) -> list[str]:
        """Get all inputs for a task (explicit + implicit from dependencies).

        Args:
            task: Task to get inputs for

        Returns:
            List of input glob patterns
        """
        all_inputs = list(task.inputs)
        implicit_inputs = get_implicit_inputs(self.recipe, task)
        all_inputs.extend(implicit_inputs)
        return all_inputs

    def _check_inputs_changed(
        self, task: Task, cached_state: TaskState, all_inputs: list[str]
    ) -> list[str]:
        """Check if any input files have changed since last run.

        Args:
            task: Task to check
            cached_state: Cached state from previous run
            all_inputs: All input glob patterns

        Returns:
            List of changed file paths
        """
        changed_files = []

        # Expand glob patterns
        input_files = self._expand_globs(all_inputs, task.working_dir)

        for file_path in input_files:
            file_path_obj = self.recipe.project_root / task.working_dir / file_path
            if not file_path_obj.exists():
                continue

            current_mtime = file_path_obj.stat().st_mtime

            # Check if file is in cached state
            cached_mtime = cached_state.input_state.get(file_path)
            if cached_mtime is None or current_mtime > cached_mtime:
                changed_files.append(file_path)

        return changed_files

    def _check_outputs_missing(self, task: Task) -> list[str]:
        """Check if any declared outputs are missing.

        Args:
            task: Task to check

        Returns:
            List of output patterns that have no matching files
        """
        if not task.outputs:
            return []

        missing_patterns = []
        base_path = self.recipe.project_root / task.working_dir

        for pattern in task.outputs:
            # Check if pattern has any matches
            matches = list(base_path.glob(pattern))
            if not matches:
                missing_patterns.append(pattern)

        return missing_patterns

    def _expand_globs(self, patterns: list[str], working_dir: str) -> list[str]:
        """Expand glob patterns to actual file paths.

        Args:
            patterns: List of glob patterns
            working_dir: Working directory to resolve patterns from

        Returns:
            List of file paths (relative to working_dir)
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
        """Update state after task execution.

        Args:
            task: Task that was executed
            args_dict: Arguments used for execution
        """
        # Compute hashes (include effective environment)
        effective_env = self._get_effective_env_name(task)
        task_hash = hash_task(task.cmd, task.outputs, task.working_dir, task.args, effective_env)
        args_hash = hash_args(args_dict) if args_dict else None
        cache_key = make_cache_key(task_hash, args_hash)

        # Get all inputs and their current mtimes
        all_inputs = self._get_all_inputs(task)
        input_files = self._expand_globs(all_inputs, task.working_dir)

        input_state = {}
        for file_path in input_files:
            file_path_obj = self.recipe.project_root / task.working_dir / file_path
            if file_path_obj.exists():
                input_state[file_path] = file_path_obj.stat().st_mtime

        # Create new state
        state = TaskState(
            last_run=time.time(),
            input_state=input_state,
        )

        # Save state
        self.state.set(cache_key, state)
        self.state.save()
