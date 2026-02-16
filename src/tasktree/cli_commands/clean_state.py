"""Clean state command implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from tasktree.cli_commands import get_action_success_string
from tasktree.logging import Logger
from tasktree.parser import find_recipe_file


def clean_state(logger: Logger, tasks_file: Optional[str] = None) -> None:
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
