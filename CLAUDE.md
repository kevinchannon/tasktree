# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Task Tree (tt) is a task automation tool that combines simple command execution with intelligent dependency tracking and incremental execution. The project is a Python application built with a focus on:

- **Intelligent incremental execution**: Tasks only run when necessary based on input changes, dependency updates, or task definition changes
- **YAML-based task definition**: Tasks are defined in `tasktree.yaml` or `tt.yaml` files with dependencies, inputs, outputs, and commands
- **Automatic input inheritance**: Tasks automatically inherit inputs from dependencies
- **Parameterized tasks**: Tasks can accept typed arguments with defaults
- **File imports**: Task definitions can be split across multiple files and namespaced

## Architecture

### Core Components

- **`src/tasktree/tasks.py`**: Core task execution logic using subprocess to run shell commands
- **`src/tasktree/cli.py`**: Command-line interface (currently minimal)
- **`main.py`**: Entry point for the application
- **`tests/unit/test_tasks.py`**: Unit tests using Python's unittest framework

### Key Dependencies

- **PyYAML**: For recipe parsing
- **Typer, Click, Rich**: For CLI (mentioned in README but not yet implemented)
- **graphlib.TopologicalSorter**: For dependency resolution
- **pathlib**: For file operations and glob expansion

## Development Commands

### Testing
```bash
python -m pytest tests/
```

### Running the Application
```bash
python main.py
```

### Package Management
This project uses `uv` for dependency management (indicated by `uv.lock` file).

## State Management

The application uses a `.tasktree-state` file at the project root to track:
- When tasks last ran
- Timestamps of input files at execution time
- Task hashes based on command, outputs, and working directory

## Testing Approach

The project uses Python's built-in `unittest` framework with mocking via `unittest.mock`. Tests focus on verifying subprocess calls for task execution.

## Task Definition Format

Tasks are defined in YAML with the following structure:
```yaml
tasks:
  task-name:
    desc: Description (optional)
    deps: [dependency-tasks]
    inputs: [glob-patterns]
    outputs: [glob-patterns]
    working_dir: execution-directory
    args: [typed-parameters]
    cmd: shell-command
```