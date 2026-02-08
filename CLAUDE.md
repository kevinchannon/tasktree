# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Task Tree (tt) is a task automation tool that combines simple command execution with intelligent dependency tracking and incremental execution. The project is a Python application built with a focus on:

- **Intelligent incremental execution**: Tasks only run when necessary based on input changes, dependency updates, or task definition changes
- **YAML-based task definition**: Tasks are defined in `tasktree.yaml` or `tt.yaml` files with dependencies, inputs, outputs, and commands
- **Automatic input inheritance**: Tasks automatically inherit inputs from dependencies
- **Parameterized tasks**: Tasks can accept typed arguments with defaults and constraints (int, float, bool, str, path, datetime, hostname, email, IP addresses)
- **File imports**: Task definitions can be split across multiple files and namespaced
- **Runner definitions**: Named execution runners (shell with custom configuration, or Docker containers with full image building support)
- **Template substitution**: Rich variable system with access to arguments, environment variables, built-in variables, dependency outputs, and task inputs/outputs
- **Docker support**: Full Docker integration with volume mounts, port mappings, build arguments, and user mapping
- **Named inputs/outputs**: Reference specific inputs and outputs by name for better clarity and DRY principles

## IMPORTANT! Development philosophies

### Small, incremental changes
The project team requires that each commit contains a small number of changes. Ideally, just the addition of a new line or statement in the code and an accompanying unit test (or tests) that validate the functionality of that line.

Tickets and features should be iteratively broken down until they can be implemented as a series of small commits.

When prompting the user to move to the next stage, estimate the size of the work and indicate whether you think there is sufficient usage to implement the next stage, or not. ("estimated required tokens: X, remaining usage in this session: Y tokens")

#### Local Claude Code work 
When working locally on a user's machine, Claude Code should NEVER make commits - only stop and ask the user to review and commit, before carrying on with the next incremental change.

#### GitHub Claude Code integration work
When working as a GitHub agent, claude should still BREAK DOWN THE TASK into small, incremental commits, but commit those changes to the feature branch as they are made. GitHub integration Claude Code does not need to ask for permission to commit each change.

### Write tests, not ad hoc test scripts
If you are checking that a feature you are implementing has been implemented correctly, DO NOT write a bespoke test script to check the output of the app with the new functionality. INSTEAD, write a unit/integration/end-to-end test that will confirm you have correctly implemented the feature and RUN JUST THAT TEST. If it passes, you have implemented things correctly; and you can either carry on with additional parts of the feature, or run all the tests to ensure no regressions.

It is still permissible to write and run an ad hoc script to investigate/confirm the current behaviour. Although, it is better to first search for a test that does the thing that you're investigating. If one exists and is passing: then the app does the thing.

### Skipping tests for all platforms is not acceptable
We DO NOT introduce `unittest.skip`, or its variants into the codebase. SOMETIMES, it is permissible to skip tests under some specific condition (e.g. docker is not available for MacOS in CI). Use `unittest.skipUnless` for this (rare) eventuality.

### Test as we go!
We do not plan to implement all the code (maybe even with unit tests) and then write a bunch of integration tests. We PLAN END-TO-END incremental changes. This will involve writing high-level test of the functionality as early as possible, to ensure that the new feature is progressing as expected.

### Try to be efficient with token usage
Your sponsor is not made of money! Try to minimise token useage, so that we can maximise the effectiveness of Claude Code on a features per token basis. Obviously, if a thing needs doing and it takes a bunch of tokens, that's just the way it is. Just try to consider/avoid profligacy!

### Architectural philosophies

- Try to follow SOLID principles
- Try to follow the advice in "Clean Code", by Robert Martin.
- Try to keep algorithmic logic abstracted from the TYPES that the logic can be run on. This is a restatement of the Liskov Substitution principle covered in the SOLID principles
- **Small, named functions are preferred over comments**.  If a comment on WHAT the code is doing feels warranted, then refactor that code into a function with an indicative name.  Comment on WHY code is like it is are more permissible.

## Architecture

### Core Components

- **`src/tasktree/parser.py`** (2,415 lines): YAML recipe parsing, task and runner definitions, circular import detection, schema validation
- **`src/tasktree/executor.py`** (1,200 lines): Task execution logic, incremental execution engine, state tracking, built-in variables, subprocess management
- **`src/tasktree/cli.py`** (591 lines): Typer-based CLI with commands: `--list`, `--show`, `--tree`, `--force`, `--only`, `--dry-run`, `--verbose`
- **`src/tasktree/graph.py`** (545 lines): Dependency resolution using graphlib.TopologicalSorter, parameterized dependencies, cycle detection
- **`src/tasktree/docker.py`** (446 lines): Docker image building and container execution, user mapping, volume mounts, build args
- **`src/tasktree/substitution.py`** (374 lines): Template variable substitution engine supporting multiple prefixes (var, arg, env, tt, dep, self)
- **`src/tasktree/types.py`** (139 lines): Custom Click parameter types for argument validation (hostname, email, IP, IPv4, IPv6, datetime)
- **`src/tasktree/hasher.py`** (161 lines): Task hashing for incremental execution, cache key generation, runner definition hashing
- **`src/tasktree/state.py`** (119 lines): State file management (.tasktree-state), task execution state tracking

### Key Dependencies

- **PyYAML**: For recipe parsing
- **Typer, Click, Rich**: For CLI and rich terminal output
- **graphlib.TopologicalSorter**: For dependency resolution
- **pathlib**: For file operations and glob expansion
- **docker (Python SDK)**: For Docker image building and container management
- **jsonschema**: For YAML schema validation

## Development Commands

## IMPORTANT! Tool use
### Athena Code Knowledge
This repo uses Athena to store and retrieve knowledge about the codebase. YOU SHOULD USE THE TOOL TO MAKE INQUIRIES ABOUT THE CODE.

1. Find a function/class: `athena locate <function/class name>`
2. Find information about what a function/class does:
   - `athena info path/to/module.py:ClassName`
   - `athena info path/to/module.py:ClassName.method`
   - `athena info path/to/module.py:some_function`
3. Search for relevant code information:
   - `athena serch "generate JWT authentication tokens`
4. AFTER code changes, run `athena status` to check which docs should have been updated
5. AFTER checking/updating docs, run `athena sync` to register the changes

**prefer this workflow to using native `grep` and `find` tools** for understanding the code.

### Testing
```bash
python3 -m pytest tests/
```
The project has tests across three categories:
- **Unit tests** (`tests/unit/`): Should always be updated for any change. Makes up the bulk of code coverage
- **Integration tests** (`tests/integration/`): Test changes using the Typer CliRunner to cover end-to-end workflows across multiple modules
- **E2E tests** (`tests/e2e/`): Heavyweight tests that cover running the tool in a subprocess and/or containerized environment 

### Running the Application
```bash
python3 main.py [task-names] [--options]
```

### Package Management
This project uses `uv` for dependency management (indicated by `uv.lock` file). Configuration is in `pyproject.toml`.

## State Management

The application uses a `.tasktree-state` file at the project root to track:
- When tasks last ran
- Timestamps of input files at execution time
- Task hashes based on command, outputs, working directory, arguments, and runner definitions
- Cached results for incremental execution

## Testing Approach

The project uses Python's built-in `unittest` framework with:
- `unittest.mock` for mocking subprocess calls and external dependencies
- `click.testing.CliRunner` for CLI testing
- Comprehensive coverage across unit, integration, and E2E test layers
- Tests verify subprocess calls, Docker operations, state management, and CLI behavior

## Task Definition Format

Tasks are defined in YAML with the following structure:
```yaml
tasks:
  task-name:
    desc: Description (optional)
    deps: [dependency-tasks]  # Can include parameterized dependencies: dep-name(arg1, key=value)
    inputs:
      - pattern1  # Anonymous glob patterns
      - name: glob-pattern  # Named inputs for reference
    outputs:
      - pattern1  # Anonymous glob patterns
      - name: path-or-pattern  # Named outputs for reference
    working_dir: execution-directory
    run_in: runner-name  # Reference to runner definition
    args:
      - name: arg-name
        type: str|int|float|bool|path|datetime|hostname|email|ip|ipv4|ipv6
        default: value
        choices: [option1, option2]  # Optional constraint
        min: value  # Optional for numeric types
        max: value  # Optional for numeric types
        exported: true  # Export as $ARG_NAME environment variable
    cmd: shell-command  # Can use {{ var.name }}, {{ arg.name }}, {{ env.NAME }}, {{ tt.* }}, {{ dep.task.outputs.name }}, {{ self.inputs.name }}
    private: true  # Hide from --list but still executable

runners:
  runner-name:
    default: true  # Make this the default runner
    shell: /bin/bash  # Shell runner
    preamble: |  # Optional preamble prepended to all commands
      set -euo pipefail
    # OR
    dockerfile: path/to/Dockerfile  # Docker runner
    context: build-context-dir
    image: optional-image-name
    volumes:
      - host_path:container_path[:ro]
    ports:
      - "host:container"
    build_args:
      ARG_NAME: value
    environment:
      ENV_VAR: value

variables:
  var-name: value  # Simple string value
  var-from-env: { env: ENV_VAR, default: fallback }  # From environment
  var-from-eval: { eval: "command to run" }  # Runtime command evaluation
  var-from-file: { read: path/to/file }  # Read file contents
```

## Built-in Variables

Tasks have access to these built-in template variables:
- `{{ tt.project_root }}`: Root directory of the project
- `{{ tt.recipe_dir }}`: Directory containing the recipe file
- `{{ tt.task_name }}`: Name of the current task
- `{{ tt.working_dir }}`: Working directory for task execution
- `{{ tt.timestamp }}`: ISO 8601 timestamp
- `{{ tt.timestamp_unix }}`: Unix timestamp
- `{{ tt.user_home }}`: User's home directory
- `{{ tt.user_name }}`: Current username

## Key Features

### Template Substitution
Commands and paths support template substitution with multiple prefixes:
- `{{ var.name }}`: Variables defined in the `variables` section
- `{{ arg.name }}`: Task arguments passed on command line
- `{{ env.NAME }}`: Environment variables
- `{{ tt.* }}`: Built-in variables (see above)
- `{{ dep.task_name.outputs.output_name }}`: Outputs from dependency tasks
- `{{ self.inputs.input_name }}`: Named inputs of the current task
- `{{ self.outputs.output_name }}`: Named outputs of the current task

### Parameterized Dependencies
Tasks can pass arguments to their dependencies:
```yaml
tasks:
  caller:
    deps:
      - dependency(value1, key=value2)  # Positional and named args
```

### Docker Integration
Full Docker support with:
- Dockerfile-based image building
- Volume mounts (read-only and read-write)
- Port mappings
- User mapping (run as non-root on Unix/macOS)
- Build arguments separate from shell arguments
- Environment variable injection

### Schema Validation
The project includes JSON Schema definitions in `schema/` for validating recipe YAML files.