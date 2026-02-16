"""Command-line interface for Task Tree.

Provides a Typer-based CLI with commands for listing, showing, executing,
and managing task definitions. Supports task execution with incremental builds,
dependency resolution, and rich terminal output via the Rich library.
"""

from __future__ import annotations

from typing import List, Optional

import click
import typer
from rich.console import Console

from tasktree import __version__
from tasktree.cli_commands.clean_state import clean_state
from tasktree.cli_commands.execute_dynamic_task import execute_dynamic_task
from tasktree.cli_commands.init_recipe import init_recipe
from tasktree.cli_commands.list_tasks import list_tasks
from tasktree.cli_commands.show_task import show_task
from tasktree.cli_commands.show_tree import show_tree
from tasktree.console_logger import ConsoleLogger
from tasktree.logging import LogLevel
from tasktree.parser import get_recipe
from tasktree.process_runner import TaskOutputTypes

app = typer.Typer(
    help="Task Tree - A task automation tool with intelligent incremental execution",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()



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
        show_task(logger, show, tasks_file, runner_override=runner)
        raise typer.Exit()

    if tree:
        show_tree(logger, tree, tasks_file)
        raise typer.Exit()

    if init:
        init_recipe(logger)
        raise typer.Exit()

    if clean:
        clean_state(logger, tasks_file)
        raise typer.Exit()

    if task_args:
        # --only implies --force
        force_execution = force or only or False
        execute_dynamic_task(
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



def cli():
    """
    Entry point for the CLI.
    @athena: 3b3cccd1ff6f
    """
    app()


if __name__ == "__main__":
    app()
