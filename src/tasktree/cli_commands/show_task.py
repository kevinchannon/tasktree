from __future__ import annotations

from typing import Optional

import typer
import yaml
from rich.syntax import Syntax

from tasktree.logging import Logger
from tasktree.parser import get_recipe


def show_task(logger: Logger, task_name: str, tasks_file: Optional[str] = None):
    """
    Show task definition with syntax highlighting.
    @athena: a6b71673d4b7
    """
    # Pass task_name as root_task for lazy variable evaluation
    recipe = get_recipe(logger, tasks_file, root_task=task_name)
    if recipe is None:
        logger.error(
            "[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]",
        )
        raise typer.Exit(1)

    task = recipe.get_task(task_name)
    if task is None:
        logger.error(f"[red]Task not found: {task_name}[/red]")
        raise typer.Exit(1)

    # Show source file info
    logger.info(f"[bold]Task: {task_name}[/bold]")
    if task.source_file:
        logger.info(f"Source: {task.source_file}\n")

    # Create YAML representation
    task_yaml = {
        task_name: {
            "desc": task.desc,
            "deps": task.deps,
            "inputs": task.inputs,
            "outputs": task.outputs,
            "working_dir": task.working_dir,
            "args": task.args,
            "cmd": task.cmd,
        }
    }

    # Remove empty fields for cleaner display
    task_dict = task_yaml[task_name]
    task_yaml[task_name] = {k: v for k, v in task_dict.items() if v}

    # Configure YAML dumper to use literal block style for multiline strings
    def literal_presenter(dumper, data):
        """Use literal block style (|) for strings containing newlines."""
        if "\n" in data:
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    yaml.add_representer(str, literal_presenter)

    # Format and highlight using Rich
    yaml_str = yaml.dump(task_yaml, default_flow_style=False, sort_keys=False)
    syntax = Syntax(yaml_str, "yaml", theme="ansi_light", line_numbers=False)
    logger.info(syntax)
