"""Command-line interface for Task Tree.

Provides a Typer-based CLI with commands for listing, showing, executing,
and managing task definitions. Supports task execution with incremental builds,
dependency resolution, and rich terminal output via the Rich library.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import click
import typer
from rich.console import Console

from tasktree import __version__
from tasktree.cli_commands.list_tasks import list_tasks
from tasktree.cli_commands.show_task import show_task
from tasktree.cli_commands.show_tree import show_tree
from tasktree.executor import Executor
from tasktree.graph import (
    resolve_execution_order,
    resolve_dependency_output_references,
    resolve_self_references,
)
from tasktree.hasher import hash_task
from tasktree.console_logger import ConsoleLogger, Logger
from tasktree.logging import LogLevel
from tasktree.parser import find_recipe_file, get_recipe, parse_task_args
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager

app = typer.Typer(
    help="Task Tree - A task automation tool with intelligent incremental execution",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def _supports_unicode() -> bool:
    """
    Check if the terminal supports Unicode characters.

    Returns:
    True if terminal supports UTF-8, False otherwise
    @athena: 68f62a942a95
    """
    # Hard stop: classic Windows console (conhost)
    if os.name == "nt" and "WT_SESSION" not in os.environ:
        return False

    # Encoding check
    encoding = sys.stdout.encoding
    if not encoding:
        return False

    try:
        "✓✗".encode(encoding)
        return True
    except UnicodeEncodeError:
        return False


def get_action_success_string() -> str:
    """
    Get the appropriate success symbol based on terminal capabilities.

    Returns:
    Unicode tick symbol (✓) if terminal supports UTF-8, otherwise "[ OK ]"
    @athena: 39d9966ee6c8
    """
    return "✓" if _supports_unicode() else "[ OK ]"


def get_action_failure_string() -> str:
    """
    Get the appropriate failure symbol based on terminal capabilities.

    Returns:
    Unicode cross symbol (✗) if terminal supports UTF-8, otherwise "[ FAIL ]"
    @athena: 5dd1111f8d74
    """
    return "✗" if _supports_unicode() else "[ FAIL ]"


def _init_recipe(logger: Logger):
    """
    Create a blank recipe file with commented examples.
    @athena: f05c0eb014d4
    """
    recipe_path = Path("tasktree.yaml")
    if recipe_path.exists():
        logger.error("[red]tasktree.yaml already exists[/red]")
        raise typer.Exit(1)

    template = """# Task Tree Recipe
# See https://github.com/kevinchannon/tasktree for documentation

# Example task definitions:

tasks:
  # build:
  #   desc: Compile the application
  #   outputs: [target/release/bin]
  #   cmd: cargo build --release

  # test:
  #   desc: Run tests
  #   deps: [build]
  #   cmd: cargo test

  # deploy:
  #   desc: Deploy to environment
  #   deps: [build]
  #   args:
  #     - environment
  #     - region: { default: eu-west-1 }
  #   cmd: |
  #     echo "Deploying to {{ arg.environment }} in {{ arg.region }}"
  #     ./deploy.sh {{ arg.environment }} {{ arg.region }}

# Uncomment and modify the examples above to define your tasks
"""

    recipe_path.write_text(template)
    logger.info(f"[green]Created {recipe_path}[/green]")
    logger.info("Edit the file to define your tasks")


def _version_callback(value: bool):
    """
    Show version and exit.
    @athena: abaed96ac23b
    """
    if value:
        console.print(f"task-tree version {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    list_opt: Optional[bool] = typer.Option(
        None, "--list", "-l", help="List all available tasks"
    ),
    show: Optional[str] = typer.Option(
        None, "--show", "-s", help="Show task definition"
    ),
    tree: Optional[str] = typer.Option(
        None, "--tree", "-t", help="Show dependency tree"
    ),
    tasks_file: Optional[str] = typer.Option(
        None, "--tasks", "-T", help="Path to recipe file (tasktree.yaml, *.tasks, etc.)"
    ),
    init: Optional[bool] = typer.Option(
        None, "--init", "-i", help="Create a blank tasktree.yaml"
    ),
    clean: Optional[bool] = typer.Option(
        None, "--clean", "-c", help="Remove state file (reset task cache)"
    ),
    force: Optional[bool] = typer.Option(
        None, "--force", "-f", help="Force re-run all tasks (ignore freshness)"
    ),
    only: Optional[bool] = typer.Option(
        None,
        "--only",
        "-o",
        help="Run only the specified task, skip dependencies (implies --force)",
    ),
    runner: Optional[str] = typer.Option(
        None, "--runner", "-r", help="Override runner for all tasks"
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        "-L",
        click_type=click.Choice(
            [l.name.lower() for l in LogLevel], case_sensitive=False
        ),
        help="""Control verbosity of tasktree's diagnostic messages""",
    ),
    task_output: Optional[str] = typer.Option(
        None,
        "--task-output",
        "-O",
        click_type=click.Choice(
            [t.value for t in TaskOutputTypes], case_sensitive=False
        ),
        help="""Control task subprocess output display:
        
        - all: show both stdout and stderr output from tasks\n
        - out: show only stdout from tasks\n
        - err: show only stderr from tasks\n
        - on-err: show stderr from tasks, but only if the task fails. (all stdout is suppressed)
        - none: suppress all output)""",
    ),
    task_args: Optional[List[str]] = typer.Argument(
        None, help="Task name and arguments"
    ),
):
    """
    Task Tree - A task automation tool with incremental execution.

    Run tasks defined in tasktree.yaml with dependency tracking
    and incremental execution.

    Configuration Files:

    Default runner settings can be configured at multiple levels (highest precedence first):

    - Project: .tasktree-config.yml at project root
    - User: ~/.config/tasktree/config.yml (Linux/macOS)
    - Machine: /etc/tasktree/config.yml (Linux/macOS)

    For Windows-specific config paths, see the README.

    Config files use the same runner schema as tasktree.yaml. The runner must be named 'default'.

    Example config file:

        runners:
          default:
            shell: zsh
            preamble: set -euo pipefail

    Examples:

    tt build                     # Run the 'build' task
    tt deploy prod region=us-1   # Run 'deploy' with arguments
    tt --list                    # List all tasks
    tt --tree test               # Show dependency tree for 'test'
    @athena: 40e6fdbe6100
    """

    logger = ConsoleLogger(console, LogLevel(LogLevel[log_level.upper()]))

    if list_opt:
        list_tasks(logger, tasks_file)
        raise typer.Exit()

    if show:
        show_task(logger, show, tasks_file)
        raise typer.Exit()

    if tree:
        show_tree(logger, tree, tasks_file)
        raise typer.Exit()

    if init:
        _init_recipe(logger)
        raise typer.Exit()

    if clean:
        _clean_state(logger, tasks_file)
        raise typer.Exit()

    if task_args:
        # --only implies --force
        force_execution = force or only or False
        _execute_dynamic_task(
            logger,
            task_args,
            force=force_execution,
            only=only or False,
            runner=runner,
            tasks_file=tasks_file,
            task_output=task_output,
        )
    else:
        recipe = get_recipe(logger, tasks_file)
        if recipe is None:
            logger.error(
                "[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]",
            )
            logger.info(
                "Run [cyan]tt --init[/cyan] to create a blank recipe file",
            )
            raise typer.Exit(1)

        logger.info("[bold]Available tasks:[/bold]")
        for task_name in sorted(recipe.task_names()):
            task = recipe.get_task(task_name)
            if task and not task.private:
                logger.info(f"  - {task_name}")
        logger.info("\nUse [cyan]tt --list[/cyan] for detailed information")
        logger.info("Use [cyan]tt <task-name>[/cyan] to run a task")


def _clean_state(logger: Logger, tasks_file: Optional[str] = None) -> None:
    """
    Remove the .tasktree-state file to reset task execution state.
    @athena: 2f270f8a2d70
    """
    if tasks_file:
        recipe_path = Path(tasks_file)
        if not recipe_path.exists():
            logger.error(f"[red]Recipe file not found: {tasks_file}[/red]")
            raise typer.Exit(1)
    else:
        recipe_path = find_recipe_file()
        if recipe_path is None:
            logger.warn("[yellow]No recipe file found[/yellow]")
            logger.info("State file location depends on recipe file location")
            raise typer.Exit(1)

    project_root = recipe_path.parent
    state_path = project_root / ".tasktree-state"

    if state_path.exists():
        state_path.unlink()
        logger.info(
            f"[green]{get_action_success_string()} Removed {state_path}[/green]",
        )
        logger.info("All tasks will run fresh on next execution")
    else:
        logger.info(f"[yellow]No state file found at {state_path}[/yellow]")


def _execute_dynamic_task(
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

    @athena: 36ae914a5bc7
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


def cli():
    """
    Entry point for the CLI.
    @athena: 3b3cccd1ff6f
    """
    app()


if __name__ == "__main__":
    app()
