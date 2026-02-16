from __future__ import annotations

from typing import Optional

import typer
from rich.tree import Tree

from tasktree import build_dependency_tree
from tasktree.logging import Logger
from tasktree.parser import get_recipe


def show_tree(logger: Logger, task_name: str, tasks_file: Optional[str] = None):
    """
    Show dependency tree structure.
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

    # Build dependency tree
    try:
        dep_tree = build_dependency_tree(recipe, task_name)
    except Exception as e:
        logger.error(f"[red]Error building dependency tree: {e}[/red]")
        raise typer.Exit(1)

    # Build Rich tree
    tree = _build_rich_tree(dep_tree)
    logger.info(tree)


def _build_rich_tree(dep_tree: dict) -> Tree:
    """
    Build a Rich Tree visualization from a dependency tree structure.

    Args:
        dep_tree: Nested dictionary representing task dependencies

    Returns:
        Rich Tree object for terminal display

    """
    task_name = dep_tree["name"]
    tree = Tree(task_name)

    # Add dependencies
    for dep in dep_tree.get("deps", []):
        dep_tree_obj = _build_rich_tree(dep)
        tree.add(dep_tree_obj)

    return tree
