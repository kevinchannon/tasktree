"""Command-line interface for Task Tree."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from tasktree import __version__
from tasktree.executor import Executor
from tasktree.graph import build_dependency_tree
from tasktree.hasher import hash_task
from tasktree.parser import Recipe, find_recipe_file, parse_arg_spec, parse_recipe
from tasktree.state import StateManager
from tasktree.types import get_click_type

app = typer.Typer(
    help="Task Tree - A task automation tool with intelligent incremental execution",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()


def _list_tasks():
    """List all available tasks with descriptions."""
    recipe = _get_recipe()
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml or tt.yaml)[/red]")
        raise typer.Exit(1)

    table = Table(title="Available Tasks")
    table.add_column("Task", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    for task_name in sorted(recipe.task_names()):
        task = recipe.get_task(task_name)
        desc = task.desc if task else ""
        table.add_row(task_name, desc)

    console.print(table)


def _show_task(task_name: str):
    """Show task definition with syntax highlighting."""
    recipe = _get_recipe()
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml or tt.yaml)[/red]")
        raise typer.Exit(1)

    task = recipe.get_task(task_name)
    if task is None:
        console.print(f"[red]Task not found: {task_name}[/red]")
        raise typer.Exit(1)

    # Show source file info
    console.print(f"[bold]Task: {task_name}[/bold]")
    if task.source_file:
        console.print(f"Source: {task.source_file}\n")

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

    # Format and highlight using Rich
    yaml_str = yaml.dump(task_yaml, default_flow_style=False, sort_keys=False)
    syntax = Syntax(yaml_str, "yaml", theme="ansi_light", line_numbers=False)
    console.print(syntax)


def _show_tree(task_name: str):
    """Show dependency tree with freshness indicators."""
    recipe = _get_recipe()
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml or tt.yaml)[/red]")
        raise typer.Exit(1)

    task = recipe.get_task(task_name)
    if task is None:
        console.print(f"[red]Task not found: {task_name}[/red]")
        raise typer.Exit(1)

    # Build dependency tree
    try:
        dep_tree = build_dependency_tree(recipe, task_name)
    except Exception as e:
        console.print(f"[red]Error building dependency tree: {e}[/red]")
        raise typer.Exit(1)

    # Get execution statuses
    state = StateManager(recipe.project_root)
    state.load()
    executor = Executor(recipe, state)
    statuses = executor.execute_task(task_name, dry_run=True)

    # Build Rich tree
    tree = _build_rich_tree(dep_tree, statuses)
    console.print(tree)


def _dry_run(task_name: str):
    """Show what would be executed without actually running."""
    recipe = _get_recipe()
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml or tt.yaml)[/red]")
        raise typer.Exit(1)

    task = recipe.get_task(task_name)
    if task is None:
        console.print(f"[red]Task not found: {task_name}[/red]")
        raise typer.Exit(1)

    # Get execution plan
    state = StateManager(recipe.project_root)
    state.load()
    executor = Executor(recipe, state)
    statuses = executor.execute_task(task_name, dry_run=True)

    # Display plan
    console.print(f"[bold]Execution plan for '{task_name}':[/bold]\n")

    will_run = [name for name, status in statuses.items() if status.will_run]
    will_skip = [name for name, status in statuses.items() if not status.will_run]

    if will_run:
        console.print(f"[yellow]Will execute ({len(will_run)} tasks):[/yellow]")
        for i, name in enumerate(will_run, 1):
            status = statuses[name]
            console.print(f"  {i}. [cyan]{name}[/cyan]")
            console.print(f"     - {status.reason}")
            if status.changed_files:
                console.print(f"     - changed files: {', '.join(status.changed_files)}")
        console.print()

    if will_skip:
        console.print(f"[green]Will skip ({len(will_skip)} tasks):[/green]")
        for name in will_skip:
            status = statuses[name]
            last_run_str = f", last run {status.last_run}" if status.last_run else ""
            console.print(f"  - {name} (fresh{last_run_str})")


def _init_recipe():
    """Create a blank recipe file with commented examples."""
    recipe_path = Path("tasktree.yaml")
    if recipe_path.exists():
        console.print("[red]tasktree.yaml already exists[/red]")
        raise typer.Exit(1)

    template = """# Task Tree Recipe
# See https://github.com/yourusername/tasktree for documentation

# Example task definitions:

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
#   args: [environment, region=eu-west-1]
#   cmd: |
#     echo "Deploying to {{environment}} in {{region}}"
#     ./deploy.sh {{environment}} {{region}}

# Uncomment and modify the examples above to define your tasks
"""

    recipe_path.write_text(template)
    console.print(f"[green]Created {recipe_path}[/green]")
    console.print("Edit the file to define your tasks")


def _show_help():
    """Display help message with all available options."""
    console.print("[bold]Task Tree - A task automation tool with intelligent incremental execution[/bold]\n")
    console.print("[bold]Usage:[/bold]")
    console.print("  tt <task-name> [args...]     Run a task")
    console.print("  tt [OPTIONS]\n")
    console.print("[bold]Options:[/bold]")
    console.print("  --help, -h                   Show this help message")
    console.print("  --version, -v                Show version")
    console.print("  --list, -l                   List all available tasks")
    console.print("  --show <task>                Show task definition")
    console.print("  --tree <task>                Show dependency tree")
    console.print("  --dry-run <task>             Show execution plan without running")
    console.print("  --init                       Create a blank tasktree.yaml")
    console.print("  --clean                      Remove state file (reset task cache)")
    console.print("  --clean-state                Remove state file (reset task cache)")
    console.print("  --reset                      Remove state file (reset task cache)\n")
    console.print("[bold]Examples:[/bold]")
    console.print("  tt build                     Run the 'build' task")
    console.print("  tt deploy prod region=us-1   Run 'deploy' with arguments")
    console.print("  tt --list                    List all tasks")
    console.print("  tt --tree test               Show dependency tree for 'test'")


def main():
    """Entry point that handles dynamic task execution."""
    import sys

    # Get command line arguments (skip the program name)
    args = sys.argv[1:]

    # Check for built-in commands
    if not args:
        # Show brief help
        recipe = _get_recipe()
        if recipe is None:
            console.print("[red]No recipe file found (tasktree.yaml or tt.yaml)[/red]")
            console.print("Run [cyan]tt --init[/cyan] to create a blank recipe file")
            raise typer.Exit(1)

        console.print("[bold]Available tasks:[/bold]")
        for task_name in sorted(recipe.task_names()):
            console.print(f"  - {task_name}")
        console.print("\nUse [cyan]tt --list[/cyan] for detailed information")
        console.print("Use [cyan]tt <task-name>[/cyan] to run a task")
        return

    if args[0] in ["--help", "-h"]:
        _show_help()
        return

    if args[0] in ["--version", "-v"]:
        console.print(f"task-tree version {__version__}")
        return

    if args[0] in ["--clean-state", "--clean", "--reset"]:
        _clean_state()
        return

    if args[0] in ["--list", "-l"]:
        _list_tasks()
        return

    if args[0] in ["--init"]:
        _init_recipe()
        return

    if args[0] in ["--show"]:
        if len(args) < 2:
            console.print("[red]Error: --show requires a task name[/red]")
            console.print("Usage: tt --show <task-name>")
            raise typer.Exit(1)
        _show_task(args[1])
        return

    if args[0] in ["--tree"]:
        if len(args) < 2:
            console.print("[red]Error: --tree requires a task name[/red]")
            console.print("Usage: tt --tree <task-name>")
            raise typer.Exit(1)
        _show_tree(args[1])
        return

    if args[0] in ["--dry-run"]:
        if len(args) < 2:
            console.print("[red]Error: --dry-run requires a task name[/red]")
            console.print("Usage: tt --dry-run <task-name>")
            raise typer.Exit(1)
        _dry_run(args[1])
        return

    # Otherwise, treat first arg as a task name
    _execute_dynamic_task(args)


def _clean_state() -> None:
    """Remove the .tasktree-state file to reset task execution state."""
    recipe_path = find_recipe_file()
    if recipe_path is None:
        console.print("[yellow]No recipe file found[/yellow]")
        console.print("State file location depends on recipe file location")
        raise typer.Exit(1)

    project_root = recipe_path.parent
    state_path = project_root / ".tasktree-state"

    if state_path.exists():
        state_path.unlink()
        console.print(f"[green]✓ Removed {state_path}[/green]")
        console.print("All tasks will run fresh on next execution")
    else:
        console.print(f"[yellow]No state file found at {state_path}[/yellow]")


def _get_recipe() -> Recipe | None:
    """Get parsed recipe or None if not found."""
    recipe_path = find_recipe_file()
    if recipe_path is None:
        return None

    try:
        return parse_recipe(recipe_path)
    except Exception as e:
        console.print(f"[red]Error parsing recipe: {e}[/red]")
        raise typer.Exit(1)


def _execute_dynamic_task(args: list[str]) -> None:
    """Execute a task specified by name with arguments.

    Args:
        args: Command line arguments (task name and task arguments)
    """
    if not args:
        return

    task_name = args[0]
    task_args = args[1:]

    recipe = _get_recipe()
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml or tt.yaml)[/red]")
        raise typer.Exit(1)

    task = recipe.get_task(task_name)
    if task is None:
        console.print(f"[red]Task not found: {task_name}[/red]")
        console.print("\nAvailable tasks:")
        for name in sorted(recipe.task_names()):
            console.print(f"  - {name}")
        raise typer.Exit(1)

    # Parse task arguments
    args_dict = _parse_task_args(task.args, task_args)

    # Prune state before execution
    state = StateManager(recipe.project_root)
    state.load()
    valid_hashes = {
        hash_task(t.cmd, t.outputs, t.working_dir, t.args)
        for t in recipe.tasks.values()
    }
    state.prune(valid_hashes)
    state.save()

    # Execute task
    executor = Executor(recipe, state)
    try:
        executor.execute_task(task_name, args_dict, dry_run=False)
        console.print(f"[green]✓ Task '{task_name}' completed successfully[/green]")
    except Exception as e:
        console.print(f"[red]✗ Task '{task_name}' failed: {e}[/red]")
        raise typer.Exit(1)


def _parse_task_args(arg_specs: list[str], arg_values: list[str]) -> dict[str, Any]:
    """Parse command line arguments for a task.

    Args:
        arg_specs: Argument specifications from task definition
        arg_values: Command line argument values

    Returns:
        Dictionary of argument names to values

    Raises:
        typer.Exit: If arguments are invalid
    """
    if not arg_specs:
        if arg_values:
            console.print(f"[red]Task does not accept arguments[/red]")
            raise typer.Exit(1)
        return {}

    # Parse argument specifications
    parsed_specs = []
    for spec in arg_specs:
        name, arg_type, default = parse_arg_spec(spec)
        parsed_specs.append((name, arg_type, default))

    # Build argument dictionary
    args_dict = {}
    positional_index = 0

    for i, value_str in enumerate(arg_values):
        # Check if it's a named argument (name=value)
        if "=" in value_str:
            arg_name, arg_value = value_str.split("=", 1)
            # Find the spec for this argument
            spec = next((s for s in parsed_specs if s[0] == arg_name), None)
            if spec is None:
                console.print(f"[red]Unknown argument: {arg_name}[/red]")
                raise typer.Exit(1)
            name, arg_type, default = spec
        else:
            # Positional argument
            if positional_index >= len(parsed_specs):
                console.print(f"[red]Too many arguments[/red]")
                raise typer.Exit(1)
            name, arg_type, default = parsed_specs[positional_index]
            arg_value = value_str
            positional_index += 1

        # Convert value to appropriate type
        try:
            click_type = get_click_type(arg_type)
            converted_value = click_type.convert(arg_value, None, None)
            args_dict[name] = converted_value
        except Exception as e:
            console.print(f"[red]Invalid value for {name}: {e}[/red]")
            raise typer.Exit(1)

    # Fill in defaults for missing arguments
    for name, arg_type, default in parsed_specs:
        if name not in args_dict:
            if default is not None:
                try:
                    click_type = get_click_type(arg_type)
                    args_dict[name] = click_type.convert(default, None, None)
                except Exception as e:
                    console.print(f"[red]Invalid default value for {name}: {e}[/red]")
                    raise typer.Exit(1)
            else:
                console.print(f"[red]Missing required argument: {name}[/red]")
                raise typer.Exit(1)

    return args_dict


def _build_rich_tree(dep_tree: dict, statuses: dict) -> Tree:
    """Build a Rich Tree from dependency tree and statuses.

    Args:
        dep_tree: Dependency tree structure
        statuses: Task execution statuses

    Returns:
        Rich Tree for display
    """
    task_name = dep_tree["name"]
    status = statuses.get(task_name)

    # Determine color based on status
    if status:
        if status.will_run:
            if status.reason == "dependency_triggered":
                color = "yellow"
                label = f"{task_name} (triggered by dependency)"
            else:
                color = "red"
                label = f"{task_name} (stale: {status.reason})"
        else:
            color = "green"
            label = f"{task_name} (fresh)"
    else:
        color = "white"
        label = task_name

    tree = Tree(f"[{color}]{label}[/{color}]")

    # Add dependencies
    for dep in dep_tree.get("deps", []):
        dep_tree_obj = _build_rich_tree(dep, statuses)
        tree.add(dep_tree_obj)

    return tree


if __name__ == "__main__":
    main()
