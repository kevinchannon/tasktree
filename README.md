# Task Tree (tt)

[![Tests](https://github.com/kevinchannon/tasktree/actions/workflows/test.yml/badge.svg)](https://github.com/YOUR_USERNAME/tasktree/actions/workflows/test.yml)

A task automation tool that combines simple command execution with intelligent dependency tracking and incremental execution.

## Installation

```bash
pipx install tasktree
```

## Quick Start

Create a `tasktree.yaml` (or `tt.yaml`) in your project:

```yaml
build:
  desc: Compile the application
  outputs: [target/release/bin]
  cmd: cargo build --release

test:
  desc: Run tests
  deps: [build]
  cmd: cargo test
```

Run tasks:

```bash
tt build          # Build the application
tt test           # Run tests (builds first if needed)
tt --list         # Show all available tasks
```

## Core Concepts

### Intelligent Incremental Execution

Task Tree only runs tasks when necessary. A task executes if:

- Its definition (command, outputs, working directory) has changed
- Any input files have changed since the last run
- Any dependencies have re-run
- It has never been executed before
- It has no inputs or outputs (always runs)

### Automatic Input Inheritance

Tasks automatically inherit inputs from dependencies, eliminating redundant declarations:

```yaml
build:
  outputs: [dist/app]
  cmd: go build -o dist/app

package:
  deps: [build]
  outputs: [dist/app.tar.gz]
  cmd: tar czf dist/app.tar.gz dist/app
  # Automatically tracks dist/app as an input
```

### Single State File

All state lives in `.tasktree-state` at your project root. Stale entries are automatically pruned—no manual cleanup needed.

## Task Definition

### Basic Structure

```yaml
task-name:
  desc: Human-readable description (optional)
  deps: [other-task]              # Task dependencies
  inputs: [src/**/*.go]            # Explicit input files (glob patterns)
  outputs: [dist/binary]           # Output files (glob patterns)
  working_dir: subproject/         # Execution directory (default: project root)
  args: [param1, param2:path=default]   # Task parameters
  cmd: go build -o dist/binary     # Command to execute
```

### Commands

Multi-line commands using YAML literal blocks:

```yaml
deploy:
  cmd: |
    mkdir -p dist
    cp build/* dist/
    rsync -av dist/ server:/opt/app/
```

Or folded blocks for long single-line commands:

```yaml
compile:
  cmd: >
    gcc -o bin/app
    src/*.c
    -I include
    -L lib -lm
```

### Parameterised Tasks

Tasks can accept arguments with optional defaults:

```yaml
deploy:
  args: [environment, region=eu-west-1]
  deps: [build]
  cmd: |
    aws s3 cp dist/app.zip s3://{{environment}}-{{region}}/
    aws lambda update-function-code --function-name app-{{environment}}
```

Invoke with: `tt deploy production` or `tt deploy staging us-east-1` or `tt deploy staging region=us-east-1`. 

Arguments may be typed, or not and have a default, or not. Valid argument types are:

* int - an integer value (e.g. 0, 10, 123, -9)
* float - a floating point value (e.g. 1.234, -3.1415, 2e-4)
* bool - Boolean-ish value (e.g. true, false, yes, no, 1, 0, etc)
* str - a string
* path - a pathlike string
* datetime - a datetime in the format 2025-12-17T16:56:12
* ip - an ip address (v4 or v6)
* ipv4 - an IPv4 value
* ipv6 - an IPv6 value
* email - String validated, but not positively confirmed to be a reachable address.
* hostname - looks like a hostname, resolution of the name is not attempted as part of the validation

Different argument values are tracked separately—tasks re-run when invoked with new arguments.

## File Imports

Split task definitions across multiple files for better organisation:

```yaml
# tasktree.yaml
import:
  - file: build/tasks.yml
    as: build
  - file: deploy/tasks.yml
    as: deploy

test:
  deps: [build.compile, build.test-compile]
  cmd: ./run-tests.sh

ci:
  deps: [build.all, test, deploy.staging]
```

Imported tasks are namespaced and can be referenced as dependencies. Each imported file is self-contained—it cannot depend on tasks in the importing file.

## Glob Patterns

Input and output patterns support standard glob syntax:

- `src/*.rs` — All Rust files in `src/`
- `src/**/*.rs` — All Rust files recursively
- `{file1,file2}` — Specific files
- `**/*.{js,ts}` — Multiple extensions recursively

## State Management

### How State Works

Each task is identified by a hash of its definition (command, outputs, working directory). State tracks:

- When the task last ran
- Timestamps of input files at that time

Tasks are re-run when their definition changes or inputs are newer than the last run.

### What's Not In The Hash

Changes to these don't invalidate cached state:

- Task name (tasks can be renamed freely)
- Description
- Dependencies (only affects execution order)
- Explicit inputs (tracked by timestamp, not definition)

### Automatic Cleanup

At the start of each invocation, state is checked for invalid task hashes and non-existent ones are automatically removed. Delete a task from your recipe file and its state disappears the next time you run `tt <cmd>`

## Example: Full Build Pipeline

```yaml
imports:
  - file: common/docker.yml
    as: docker

compile:
  desc: Build application binaries
  outputs: [target/release/app]
  cmd: cargo build --release

test-unit:
  desc: Run unit tests
  deps: [compile]
  cmd: cargo test

package:
  desc: Create distribution archive
  deps: [compile]
  outputs: [dist/app-{{version}}.tar.gz]
  args: [version]
  cmd: |
    mkdir -p dist
    tar czf dist/app-{{version}}.tar.gz \
      target/release/app \
      config/ \
      migrations/

deploy:
  desc: Deploy to environment
  deps: [package, docker.build-runtime]
  args: [environment, version]
  cmd: |
    scp dist/app-{{version}}.tar.gz {{environment}}:/opt/
    ssh {{environment}} /opt/deploy.sh {{version}}

integration-test:
  desc: Run integration tests against deployed environment
  deps: [deploy]
  args: [environment, version]
  cmd: pytest tests/integration/ --env={{environment}}
```

Run the full pipeline:

```bash
tt integration-test staging version=1.2.3
```

This will:
1. Compile if sources have changed
2. Run unit tests if compilation ran
3. Package if compilation ran or version argument is new
4. Build Docker runtime (from imported file) if needed
5. Deploy if package or Docker image changed
6. Run integration tests (always runs)

## Implementation Notes

Built with Python 3.11+ using:

- **PyYAML** for recipe parsing
- **Typer**, **Click**, **Rich** for CLI
- **graphlib.TopologicalSorter** for dependency resolution
- **pathlib** for file operations and glob expansion

State file uses JSON format for simplicity and standard library compatibility.