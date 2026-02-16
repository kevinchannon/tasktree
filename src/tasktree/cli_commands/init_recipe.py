"""Initialize a new tasktree recipe file."""

from __future__ import annotations

from pathlib import Path

import typer

from tasktree.logging import Logger


def init_recipe(logger: Logger):
    """
    Create a blank recipe file with commented examples.
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
