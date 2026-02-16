"""Execute dynamic task command implementation."""

from __future__ import annotations

from typing import Optional

import typer

from tasktree.cli_commands import get_action_success_string, get_action_failure_string
from tasktree.executor import Executor
from tasktree.graph import (
    resolve_execution_order,
    resolve_dependency_output_references,
    resolve_self_references,
)
from tasktree.hasher import hash_task
from tasktree.logging import Logger
from tasktree.parser import get_recipe, parse_task_args
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager


def execute_dynamic_task(
    logger: Logger,
    args: list[str],
    force: bool = False,
    only: bool = False,
    runner: Optional[str] = None,
    tasks_file: Optional[str] = None,
    task_output: str | None = None,
) -> None:
    """
    Execute a task with its dependencies and handle argument parsing.

    Args:
    logger: Logger interface for output
    args: Task name followed by optional task arguments
    force: Force re-execution even if task is up-to-date
    only: Execute only the specified task, skip dependencies
    runner: Override runner for task execution
    tasks_file: Path to recipe file (optional)
    task_output: Control task subprocess output (all, out, err, on-err, none)

    """
    if not args:
        return

    task_name = args[0]
    task_args = args[1:]

    # Pass task_name as root_task for lazy variable evaluation
    recipe = get_recipe(logger, tasks_file, root_task=task_name)
    if recipe is None:
        logger.error(
            "[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]",
        )
        raise typer.Exit(1)

    # Apply global runner override if provided
    if runner:
        # Validate that the runner exists
        if not recipe.get_runner(runner):
            logger.error(f"[red]Runner not found: {runner}[/red]")
            logger.info("\nAvailable runners:")
            for env_name in sorted(recipe.runners.keys()):
                logger.info(f"  - {env_name}")
            raise typer.Exit(1)
        recipe.global_runner_override = runner

    task = recipe.get_task(task_name)
    if task is None:
        logger.error(f"[red]Task not found: {task_name}[/red]")
        logger.info("\nAvailable tasks:")
        for name in sorted(recipe.task_names()):
            task = recipe.get_task(name)
            if task and not task.private:
                logger.info(f"  - {name}")
        raise typer.Exit(1)

    # Parse task arguments
    args_dict = parse_task_args(logger, task.args, task_args)

    # Create executor and state manager
    state = StateManager(recipe.project_root, logger)
    state.load()
    executor = Executor(recipe, state, logger, make_process_runner)

    # Resolve execution order to determine which tasks will actually run
    # This is important for correct state pruning after template substitution
    execution_order = resolve_execution_order(recipe, task_name, args_dict)

    try:
        # Resolve dependency output references in topological order
        # This substitutes {{ dep.*.outputs.* }} templates before execution
        resolve_dependency_output_references(recipe, execution_order)

        # Resolve self-references in topological order
        # This substitutes {{ self.inputs.* }} and {{ self.outputs.* }} templates
        resolve_self_references(recipe, execution_order)
    except ValueError as e:
        logger.error(f"[red]Error in task template: {e}[/red]")
        raise typer.Exit(1)

    # Prune state based on tasks that will actually execute (with their specific arguments)
    # This ensures template-substituted dependencies are handled correctly
    valid_hashes = set()
    for _, task in recipe.tasks.items():
        # Compute base task hash
        task_hash = hash_task(
            task.cmd,
            task.outputs,
            task.working_dir,
            task.args,
            executor._get_effective_runner_name(task),
            task.deps,
        )

        valid_hashes.add(task_hash)

    state.prune(valid_hashes)
    state.save()
    try:
        executor.execute_task(
            task_name,
            TaskOutputTypes(task_output.lower()) if task_output is not None else None,
            args_dict,
            force=force,
            only=only,
        )
        logger.info(
            f"[green]{get_action_success_string()} Task '{task_name}' completed successfully[/green]",
        )
    except Exception as e:
        logger.error(
            f"[red]{get_action_failure_string()} Task '{task_name}' failed: {e}[/red]"
        )
        raise typer.Exit(1)
