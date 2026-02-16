from __future__ import annotations

from typing import Optional

import typer
from rich.table import Table

from tasktree import parse_arg_spec
from tasktree.parser import get_recipe
from tasktree.logging import Logger


def list_tasks(logger: Logger, tasks_file: Optional[str] = None):
    """
    List all available tasks with descriptions.
    """
    recipe = get_recipe(logger, tasks_file)
    if recipe is None:
        logger.error(
            "[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]",
        )
        raise typer.Exit(1)

    # Calculate maximum task name length for fixed-width column (only visible tasks)
    visible_task_names = []
    for name in recipe.task_names():
        task = recipe.get_task(name)
        if task and not task.private:
            visible_task_names.append(name)
    max_task_name_len = (
        max(len(name) for name in visible_task_names) if visible_task_names else 0
    )

    # Create borderless table with three columns
    table = Table(show_edge=False, show_header=False, box=None, padding=(0, 2))

    # Command column: fixed width to accommodate the longest task name
    table.add_column(
        "Command", style="bold cyan", no_wrap=True, width=max_task_name_len
    )

    # Arguments column: allow wrapping with sensible max width
    table.add_column("Arguments", style="white", max_width=60)

    # Description column: allow wrapping with sensible max width
    table.add_column("Description", style="white", max_width=80)

    for task_name in sorted(recipe.task_names()):
        task = recipe.get_task(task_name)
        # Skip private tasks in list output
        if task and task.private:
            continue
        desc = task.desc if task else ""
        args_formatted = _format_task_arguments(task.args) if task else ""

        table.add_row(task_name, args_formatted, desc)

    logger.info(table)


def _format_task_arguments(arg_specs: list[str | dict]) -> str:
    """
    Format task arguments for display in list output.

    Args:
    arg_specs: List of argument specifications from task definition (strings or dicts)

    Returns:
    Formatted string showing arguments with types and defaults

    Examples:
    ["mode", "target"] -> "mode:str target:str"
    ["mode=debug", "target=x86_64"] -> "mode:str [=debug] target:str [=x86_64]"
    ["port:int", "debug:bool=false"] -> "port:int debug:bool [=false]"
    [{"timeout": {"type": "int", "default": 30}}] -> "timeout:int [=30]"
    """
    if not arg_specs:
        return ""

    formatted_parts = []
    for spec_str in arg_specs:
        parsed = parse_arg_spec(spec_str)

        # Format: name:type or name:type [=default]
        # Argument names in normal intensity, types and defaults in dim
        arg_part = f"{parsed.name}[dim]:{parsed.arg_type}[/dim]"

        if parsed.default is not None:
            # Use dim styling for the default value part
            arg_part += f" [dim]\\[={parsed.default}][/dim]"

        formatted_parts.append(arg_part)

    return " ".join(formatted_parts)
