from __future__ import annotations

from typing import Optional

import typer
import yaml
from rich.syntax import Syntax

from tasktree.logging import Logger
from tasktree.parser import Recipe, Task, get_recipe


def _resolve_effective_runner(recipe: Recipe, task: Task) -> Optional[str]:
    """
    Resolve the effective runner name for a task, following precedence rules.

    Resolution order:
    1. Recipe's global_runner_override (from CLI --runner)
    2. Task's explicit run_in field (includes blanket runner if applied)
    3. Recipe's default_runner
    4. None (indicating session default will be used)

    Returns:
        Runner name, or None if session default applies
    """
    # Check for global override first (but respect pinned tasks indirectly
    # since pinned tasks won't be overridden by blanket runners, only CLI)
    if recipe.global_runner_override:
        return recipe.global_runner_override

    # Use task's runner
    if task.run_in:
        return task.run_in

    # Use recipe default
    if recipe.default_runner:
        return recipe.default_runner

    # Session default (don't display as it's platform-specific)
    return None


def show_task(logger: Logger, task_name: str, tasks_file: Optional[str] = None, runner_override: Optional[str] = None):
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

    # Apply runner override if specified
    if runner_override:
        recipe.global_runner_override = runner_override

    # Show source file info
    logger.info(f"[bold]Task: {task_name}[/bold]")
    if task.source_file:
        logger.info(f"Source: {task.source_file}")

    # Resolve and display effective runner
    effective_runner = _resolve_effective_runner(recipe, task)
    if effective_runner:
        logger.info(f"Effective runner: {effective_runner}\n")
    else:
        logger.info("")

    # Create YAML representation
    task_yaml = {
        task_name: {
            "desc": task.desc,
            "deps": task.deps,
            "inputs": task.inputs,
            "outputs": task.outputs,
            "working_dir": task.working_dir,
            "run_in": task.run_in,
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
