from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

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
    no_args_is_help=True,
)
console = Console()


def _list_tasks(tasks_file: Optional[str] = None):
    """List all available tasks with descriptions."""
    recipe = _get_recipe(tasks_file)
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]")
        raise typer.Exit(1)

    table = Table(title="Available Tasks")
    table.add_column("Task", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    for task_name in sorted(recipe.task_names()):
        task = recipe.get_task(task_name)
        desc = task.desc if task else ""
        table.add_row(task_name, desc)

    console.print(table)


def _show_task(task_name: str, tasks_file: Optional[str] = None):
    """Show task definition with syntax highlighting."""
    recipe = _get_recipe(tasks_file)
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]")
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

    # Configure YAML dumper to use literal block style for multiline strings
    def literal_presenter(dumper, data):
        """Use literal block style (|) for strings containing newlines."""
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    yaml.add_representer(str, literal_presenter)

    # Format and highlight using Rich
    yaml_str = yaml.dump(task_yaml, default_flow_style=False, sort_keys=False)
    syntax = Syntax(yaml_str, "yaml", theme="ansi_light", line_numbers=False)
    console.print(syntax)


def _show_tree(task_name: str, tasks_file: Optional[str] = None):
    """Show dependency tree structure."""
    recipe = _get_recipe(tasks_file)
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]")
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

    # Build Rich tree
    tree = _build_rich_tree(dep_tree)
    console.print(tree)


def _init_recipe():
    """Create a blank recipe file with commented examples."""
    recipe_path = Path("tasktree.yaml")
    if recipe_path.exists():
        console.print("[red]tasktree.yaml already exists[/red]")
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
  #   args: [environment, region=eu-west-1]
  #   cmd: |
  #     echo "Deploying to {{environment}} in {{region}}"
  #     ./deploy.sh {{environment}} {{region}}

# Uncomment and modify the examples above to define your tasks
"""

    recipe_path.write_text(template)
    console.print(f"[green]Created {recipe_path}[/green]")
    console.print("Edit the file to define your tasks")


def _version_callback(value: bool):
    """Show version and exit."""
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
    list_opt: Optional[bool] = typer.Option(None, "--list", "-l", help="List all available tasks"),
    show: Optional[str] = typer.Option(None, "--show", "-s", help="Show task definition"),
    tree: Optional[str] = typer.Option(None, "--tree", "-t", help="Show dependency tree"),
    tasks_file: Optional[str] = typer.Option(None, "--tasks", "-T", help="Path to recipe file (tasktree.yaml, *.tasks, etc.)"),
    init: Optional[bool] = typer.Option(
        None, "--init", "-i", help="Create a blank tasktree.yaml"
    ),
    clean: Optional[bool] = typer.Option(
        None, "--clean", "-c", help="Remove state file (reset task cache)"
    ),
    clean_state: Optional[bool] = typer.Option(
        None, "--clean-state", "-C", help="Remove state file (reset task cache)"
    ),
    reset: Optional[bool] = typer.Option(
        None, "--reset", "-r", help="Remove state file (reset task cache)"
    ),
    force: Optional[bool] = typer.Option(
        None, "--force", "-f", help="Force re-run all tasks (ignore freshness)"
    ),
    only: Optional[bool] = typer.Option(
        None, "--only", "-o", help="Run only the specified task, skip dependencies (implies --force)"
    ),
    env: Optional[str] = typer.Option(
        None, "--env", "-e", help="Override environment for all tasks"
    ),
    task_args: Optional[List[str]] = typer.Argument(
        None, help="Task name and arguments"
    ),
):
    """Task Tree - A task automation tool with incremental execution.

    Run tasks defined in tasktree.yaml with dependency tracking
    and incremental execution.

    Examples:

      tt build                     # Run the 'build' task
      tt deploy prod region=us-1   # Run 'deploy' with arguments
      tt --list                    # List all tasks
      tt --tree test               # Show dependency tree for 'test'
    """

    if list_opt:
        _list_tasks(tasks_file)
        raise typer.Exit()

    if show:
        _show_task(show, tasks_file)
        raise typer.Exit()

    if tree:
        _show_tree(tree, tasks_file)
        raise typer.Exit()

    if init:
        _init_recipe()
        raise typer.Exit()

    if clean or clean_state or reset:
        _clean_state(tasks_file)
        raise typer.Exit()

    if task_args:
        # --only implies --force
        force_execution = force or only or False
        _execute_dynamic_task(task_args, force=force_execution, only=only or False, env=env, tasks_file=tasks_file)
    else:
        recipe = _get_recipe(tasks_file)
        if recipe is None:
            console.print("[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]")
            console.print("Run [cyan]tt --init[/cyan] to create a blank recipe file")
            raise typer.Exit(1)

        console.print("[bold]Available tasks:[/bold]")
        for task_name in sorted(recipe.task_names()):
            console.print(f"  - {task_name}")
        console.print("\nUse [cyan]tt --list[/cyan] for detailed information")
        console.print("Use [cyan]tt <task-name>[/cyan] to run a task")


def _clean_state(tasks_file: Optional[str] = None) -> None:
    """Remove the .tasktree-state file to reset task execution state."""
    if tasks_file:
        recipe_path = Path(tasks_file)
        if not recipe_path.exists():
            console.print(f"[red]Recipe file not found: {tasks_file}[/red]")
            raise typer.Exit(1)
    else:
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


def _get_recipe(recipe_file: Optional[str] = None) -> Optional[Recipe]:
    """Get parsed recipe or None if not found.

    Args:
        recipe_file: Optional path to recipe file. If not provided, searches for recipe file.
    """
    if recipe_file:
        recipe_path = Path(recipe_file)
        if not recipe_path.exists():
            console.print(f"[red]Recipe file not found: {recipe_file}[/red]")
            raise typer.Exit(1)
        # When explicitly specified, project root is current working directory
        project_root = Path.cwd()
    else:
        try:
            recipe_path = find_recipe_file()
            if recipe_path is None:
                return None
        except ValueError as e:
            # Multiple recipe files found
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        # When auto-discovered, project root is recipe file's parent
        project_root = None

    try:
        return parse_recipe(recipe_path, project_root)
    except Exception as e:
        console.print(f"[red]Error parsing recipe: {e}[/red]")
        raise typer.Exit(1)


def _execute_dynamic_task(args: list[str], force: bool = False, only: bool = False, env: Optional[str] = None, tasks_file: Optional[str] = None) -> None:
    if not args:
        return

    task_name = args[0]
    task_args = args[1:]

    recipe = _get_recipe(tasks_file)
    if recipe is None:
        console.print("[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]")
        raise typer.Exit(1)

    # Apply global environment override if provided
    if env:
        # Validate that the environment exists
        if not recipe.get_environment(env):
            console.print(f"[red]Environment not found: {env}[/red]")
            console.print("\nAvailable environments:")
            for env_name in sorted(recipe.environments.keys()):
                console.print(f"  - {env_name}")
            raise typer.Exit(1)
        recipe.global_env_override = env

    task = recipe.get_task(task_name)
    if task is None:
        console.print(f"[red]Task not found: {task_name}[/red]")
        console.print("\nAvailable tasks:")
        for name in sorted(recipe.task_names()):
            console.print(f"  - {name}")
        raise typer.Exit(1)

    # Parse task arguments
    args_dict = _parse_task_args(task.args, task_args)

    # Create executor and state manager
    state = StateManager(recipe.project_root)
    state.load()
    executor = Executor(recipe, state)

    # Prune state before execution (compute hashes with effective environment)
    valid_hashes = {
        hash_task(t.cmd, t.outputs, t.working_dir, t.args, executor._get_effective_env_name(t))
        for t in recipe.tasks.values()
    }
    state.prune(valid_hashes)
    state.save()
    try:
        executor.execute_task(task_name, args_dict, force=force, only=only)
        console.print(f"[green]✓ Task '{task_name}' completed successfully[/green]")
    except Exception as e:
        console.print(f"[red]✗ Task '{task_name}' failed: {e}[/red]")
        raise typer.Exit(1)


def _parse_task_args(arg_specs: list[str], arg_values: list[str]) -> dict[str, Any]:
    if not arg_specs:
        if arg_values:
            console.print(f"[red]Task does not accept arguments[/red]")
            raise typer.Exit(1)
        return {}

    parsed_specs = []
    for spec in arg_specs:
        parsed = parse_arg_spec(spec)
        parsed_specs.append(parsed)

    args_dict = {}
    positional_index = 0

    for i, value_str in enumerate(arg_values):
        # Check if it's a named argument (name=value)
        if "=" in value_str:
            arg_name, arg_value = value_str.split("=", 1)
            # Find the spec for this argument
            spec = next((s for s in parsed_specs if s.name == arg_name), None)
            if spec is None:
                console.print(f"[red]Unknown argument: {arg_name}[/red]")
                raise typer.Exit(1)
        else:
            # Positional argument
            if positional_index >= len(parsed_specs):
                console.print(f"[red]Too many arguments[/red]")
                raise typer.Exit(1)
            spec = parsed_specs[positional_index]
            arg_value = value_str
            positional_index += 1

        # Convert value to appropriate type (exported args are always strings)
        try:
            click_type = get_click_type(spec.arg_type, min_val=spec.min_val, max_val=spec.max_val)
            converted_value = click_type.convert(arg_value, None, None)

            # Validate choices after type conversion
            if spec.choices is not None and converted_value not in spec.choices:
                console.print(f"[red]Invalid value for {spec.name}: {converted_value!r}[/red]")
                console.print(f"Valid choices: {', '.join(repr(c) for c in spec.choices)}")
                raise typer.Exit(1)

            args_dict[spec.name] = converted_value
        except typer.Exit:
            raise  # Re-raise typer.Exit without wrapping
        except Exception as e:
            console.print(f"[red]Invalid value for {spec.name}: {e}[/red]")
            raise typer.Exit(1)

    # Fill in defaults for missing arguments
    for spec in parsed_specs:
        if spec.name not in args_dict:
            if spec.default is not None:
                try:
                    click_type = get_click_type(spec.arg_type, min_val=spec.min_val, max_val=spec.max_val)
                    args_dict[spec.name] = click_type.convert(spec.default, None, None)
                except Exception as e:
                    console.print(f"[red]Invalid default value for {spec.name}: {e}[/red]")
                    raise typer.Exit(1)
            else:
                console.print(f"[red]Missing required argument: {spec.name}[/red]")
                raise typer.Exit(1)

    return args_dict


def _build_rich_tree(dep_tree: dict) -> Tree:
    task_name = dep_tree["name"]
    tree = Tree(task_name)

    # Add dependencies
    for dep in dep_tree.get("deps", []):
        dep_tree_obj = _build_rich_tree(dep)
        tree.add(dep_tree_obj)

    return tree


def cli():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    app()
