"""Command-line interface for Task Tree.

Provides a Typer-based CLI with commands for listing, showing, executing,
and managing task definitions. Supports task execution with incremental builds,
dependency resolution, and rich terminal output via the Rich library.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List, Optional

import click
import typer
import yaml
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree

from tasktree import __version__
from tasktree.executor import Executor
from tasktree.graph import (
    build_dependency_tree,
    resolve_execution_order,
    resolve_dependency_output_references,
    resolve_self_references,
)
from tasktree.hasher import hash_task, hash_args
from tasktree.console_logger import ConsoleLogger, Logger
from tasktree.logging import LogLevel
from tasktree.parser import Recipe, find_recipe_file, parse_arg_spec, parse_recipe
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager
from tasktree.types import get_click_type


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
    @athena: fc3d6da90aeb
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


def _list_tasks(logger: Logger, tasks_file: Optional[str] = None):
    """
    List all available tasks with descriptions.
    @athena: 907819fc0cc7
    """
    recipe = _get_recipe(logger, tasks_file)
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


def _show_task(logger: Logger, task_name: str, tasks_file: Optional[str] = None):
    """
    Show task definition with syntax highlighting.
    @athena: a6b71673d4b7
    """
    # Pass task_name as root_task for lazy variable evaluation
    recipe = _get_recipe(logger, tasks_file, root_task=task_name)
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


def _show_tree(logger: Logger, task_name: str, tasks_file: Optional[str] = None):
    """
    Show dependency tree structure.
    @athena: 88fbc03f4915
    """
    # Pass task_name as root_task for lazy variable evaluation
    recipe = _get_recipe(logger, tasks_file, root_task=task_name)
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
        None,
        "--only",
        "-o",
        help="Run only the specified task, skip dependencies (implies --force)",
    ),
    env: Optional[str] = typer.Option(
        None, "--env", "-e", help="Override environment for all tasks"
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
    task_output: str = typer.Option(
        "all",
        "--task-output",
        "-O",
        click_type=click.Choice([t.value for t in TaskOutputTypes], case_sensitive=False),
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

    Examples:

    tt build                     # Run the 'build' task
    tt deploy prod region=us-1   # Run 'deploy' with arguments
    tt --list                    # List all tasks
    tt --tree test               # Show dependency tree for 'test'
    @athena: 40e6fdbe6100
    """

    logger = ConsoleLogger(console, LogLevel(LogLevel[log_level.upper()]))

    if list_opt:
        _list_tasks(logger, tasks_file)
        raise typer.Exit()

    if show:
        _show_task(logger, show, tasks_file)
        raise typer.Exit()

    if tree:
        _show_tree(logger, tree, tasks_file)
        raise typer.Exit()

    if init:
        _init_recipe(logger)
        raise typer.Exit()

    if clean or clean_state or reset:
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
            env=env,
            tasks_file=tasks_file,
            task_output=task_output,
        )
    else:
        recipe = _get_recipe(logger, tasks_file)
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


def _get_recipe(
    logger: Logger, recipe_file: Optional[str] = None, root_task: Optional[str] = None
) -> Optional[Recipe]:
    """
    Get parsed recipe or None if not found.

    Args:
    logger_fn: Logger function for output
    recipe_file: Optional path to recipe file. If not provided, searches for recipe file.
    root_task: Optional root task for lazy variable evaluation. If provided, only variables
    reachable from this task will be evaluated (performance optimization).
    @athena: ded906495d18
    """
    if recipe_file:
        recipe_path = Path(recipe_file)
        if not recipe_path.exists():
            logger.error(f"[red]Recipe file not found: {recipe_file}[/red]")
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
            logger.error(f"[red]{e}[/red]")
            raise typer.Exit(1)
        # When auto-discovered, project root is recipe file's parent
        project_root = None

    try:
        return parse_recipe(recipe_path, project_root, root_task)
    except Exception as e:
        logger.error(f"[red]Error parsing recipe: {e}[/red]")
        raise typer.Exit(1)


def _execute_dynamic_task(
    logger: Logger,
    args: list[str],
    force: bool = False,
    only: bool = False,
    env: Optional[str] = None,
    tasks_file: Optional[str] = None,
    task_output: str = "all",
) -> None:
    """
    Execute a task with its dependencies and handle argument parsing.

    Args:
    logger: Logger interface for output
    args: Task name followed by optional task arguments
    force: Force re-execution even if task is up-to-date
    only: Execute only the specified task, skip dependencies
    env: Override environment for task execution
    tasks_file: Path to recipe file (optional)
    task_output: Control task subprocess output (all, out, err, on-err, none)

    @athena: 36ae914a5bc7
    """
    if not args:
        return

    task_name = args[0]
    task_args = args[1:]

    # Pass task_name as root_task for lazy variable evaluation
    recipe = _get_recipe(logger, tasks_file, root_task=task_name)
    if recipe is None:
        logger.error(
            "[red]No recipe file found (tasktree.yaml, tasktree.yml, tt.yaml, or *.tasks)[/red]",
        )
        raise typer.Exit(1)

    # Apply global environment override if provided
    if env:
        # Validate that the environment exists
        if not recipe.get_environment(env):
            logger.error(f"[red]Environment not found: {env}[/red]")
            logger.info("\nAvailable environments:")
            for env_name in sorted(recipe.environments.keys()):
                logger.info(f"  - {env_name}")
            raise typer.Exit(1)
        recipe.global_env_override = env

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
    args_dict = _parse_task_args(logger, task.args, task_args)

    # Create executor and state manager
    state = StateManager(recipe.project_root)
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
            executor._get_effective_env_name(task),
            task.deps,
        )

        valid_hashes.add(task_hash)

    state.prune(valid_hashes)
    state.save()
    try:
        executor.execute_task(
            task_name,
            TaskOutputTypes(task_output.lower()),
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


def _parse_task_args(
    logger: Logger, arg_specs: list[str], arg_values: list[str]
) -> dict[str, Any]:
    """
    Parse and validate task arguments from command line values.

    Args:
    logger: Logger interface for output
    arg_specs: Task argument specifications with types and defaults
    arg_values: Raw argument values from command line (positional or named)

    Returns:
    Dictionary mapping argument names to typed, validated values

    Raises:
    typer.Exit: If arguments are invalid, missing, or unknown

    @athena: d9a7ea55c3d6
    """
    if not arg_specs:
        if arg_values:
            logger.error("[red]Task does not accept arguments[/red]")
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
                logger.error(f"[red]Unknown argument: {arg_name}[/red]")
                raise typer.Exit(1)
        else:
            # Positional argument
            if positional_index >= len(parsed_specs):
                logger.error("[red]Too many arguments[/red]")
                raise typer.Exit(1)
            spec = parsed_specs[positional_index]
            arg_value = value_str
            positional_index += 1

        # Convert value to appropriate type (exported args are always strings)
        try:
            click_type = get_click_type(
                spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
            )
            converted_value = click_type.convert(arg_value, None, None)

            # Validate choices after type conversion
            if spec.choices is not None and converted_value not in spec.choices:
                logger.error(
                    f"[red]Invalid value for {spec.name}: {converted_value!r}[/red]",
                )
                logger.info(
                    f"Valid choices: {', '.join(repr(c) for c in spec.choices)}",
                )
                raise typer.Exit(1)

            args_dict[spec.name] = converted_value
        except typer.Exit:
            raise  # Re-raise typer.Exit without wrapping
        except Exception as e:
            logger.error(f"[red]Invalid value for {spec.name}: {e}[/red]")
            raise typer.Exit(1)

    # Fill in defaults for missing arguments
    for spec in parsed_specs:
        if spec.name not in args_dict:
            if spec.default is not None:
                try:
                    click_type = get_click_type(
                        spec.arg_type, min_val=spec.min_val, max_val=spec.max_val
                    )
                    args_dict[spec.name] = click_type.convert(spec.default, None, None)
                except Exception as e:
                    logger.error(
                        f"[red]Invalid default value for {spec.name}: {e}[/red]",
                    )
                    raise typer.Exit(1)
            else:
                logger.error(f"[red]Missing required argument: {spec.name}[/red]")
                raise typer.Exit(1)

    return args_dict


def _build_rich_tree(dep_tree: dict) -> Tree:
    """
    Build a Rich Tree visualization from a dependency tree structure.

    Args:
        dep_tree: Nested dictionary representing task dependencies

    Returns:
        Rich Tree object for terminal display

    @athena: 62472c8ca729
    """
    task_name = dep_tree["name"]
    tree = Tree(task_name)

    # Add dependencies
    for dep in dep_tree.get("deps", []):
        dep_tree_obj = _build_rich_tree(dep)
        tree.add(dep_tree_obj)

    return tree


def cli():
    """
    Entry point for the CLI.
    @athena: 3b3cccd1ff6f
    """
    app()


if __name__ == "__main__":
    app()
