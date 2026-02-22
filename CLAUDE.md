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
When working as a GitHub agent, claude should BREAK DOWN THE TASK into small, incremental commits, AND THEN COMMIT THOSE CHANGES to the feature branch as they are made. GitHub integration Claude Code DOES NOT need to ask for permission to commit each change.

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
- **`src/tasktree/lsp/`**: Language Server Protocol implementation
  - **`server.py`**: Main LSP server with pygls handlers (initialize, shutdown, completion, document tracking)
  - **`builtin_variables.py`**: Built-in variable constant definitions (tt.*)
  - **`parser_wrapper.py`**: YAML parsing for variable/argument extraction (reuses tasktree parser)
  - **`position_utils.py`**: Cursor position detection utilities (task scoping, cmd field detection)

### Key Dependencies

- **PyYAML**: For recipe parsing
- **Typer, Click, Rich**: For CLI and rich terminal output
- **graphlib.TopologicalSorter**: For dependency resolution
- **pathlib**: For file operations and glob expansion
- **docker (Python SDK)**: For Docker image building and container management
- **jsonschema**: For YAML schema validation

## Development Commands

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
    pin_runner: true  # Lock this task's runner, immune to import-level overrides

runners:
  default: runner-name  # Declare the default runner by name (optional)
  runner-name:
    shell: /bin/bash  # Shell runner
    preamble: |  # Optional preamble prepended to all commands
      set -euo pipefail
    # OR
    dockerfile: path/to/Dockerfile  # Docker runner
    context: build-context-dir
    volumes:
      - host_path:container_path[:ro]
    ports:
      - "host:container"
    args:
      ARG_NAME: value
    env_vars:
      ENV_VAR: value

variables:
  var-name: value  # Simple string value
  var-from-env: { env: ENV_VAR, default: fallback }  # From environment
  var-from-eval: { eval: "command to run" }  # Runtime command evaluation
  var-from-file: { read: path/to/file }  # Read file contents

imports:
  - file: path/to/tasks.yaml  # Import tasks from another file
    as: namespace  # Namespace prefix for imported tasks and runners
    run_in: runner-name  # Blanket runner override for all non-pinned tasks in import
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

### Runner Override for Imported Tasks
When importing task files, the importing file can control which runner imported tasks use:

**Blanket Runner Override**: Apply a default runner to all non-pinned tasks in an import:
```yaml
imports:
  - file: "build.tasks"
    as: build
    run_in: docker  # All non-pinned tasks from build.tasks use docker runner
```

**Runner Pinning**: Tasks can lock their runner to be immune to blanket overrides:
```yaml
tasks:
  special_task:
    cmd: "echo special"
    run_in: special_container
    pin_runner: true  # Ignores import-level run_in override
```

**Runner Namespacing**: Runners referenced by pinned tasks are imported and namespaced:
- If importing with `as: build`, runner `docker` becomes `build.docker`
- Prevents collisions between root and imported runner names
- Internal references in pinned tasks are automatically rewritten

**Precedence Order** (highest to lowest):
1. CLI `--runner` flag (overrides everything, including pinned runners)
2. Pinned task runner (`pin_runner: true` with `run_in`)
3. Import-level blanket runner (`imports[].run_in`)
4. Task-level `run_in` (unpinned)
5. Default runner (`default: true` in runner definition)
6. Session default runner

**Validation Rules**:
- Runner names cannot contain dots (reserved for namespacing)
- Pinned tasks must have `run_in` specified
- Pinned runner validation is lazy (occurs at task invocation, not parse time)

### Schema Validation
The project includes JSON Schema definitions in `schema/` for validating recipe YAML files.

## LSP Server Development

### Architecture Principles

The LSP server (`tt-lsp`) follows these key design principles:

1. **Parser Reuse**: The LSP server MUST reuse tasktree's own parser (`src/tasktree/parser.py`) for extracting identifiers. DO NOT reimplement YAML parsing or task/variable extraction logic.

2. **Thin Vertical Slices**: LSP features are implemented as end-to-end vertical slices, each with unit, integration, and e2e tests. Each slice delivers one complete, working feature (e.g., tt.* completion, var.* completion, arg.* completion).

3. **Small, Focused Modules**: The LSP implementation is split into small modules with single responsibilities:
   - `server.py` - LSP protocol handlers only
   - `parser_wrapper.py` - YAML parsing and identifier extraction only
   - `position_utils.py` - Cursor position detection only
   - `builtin_variables.py` - Constant definitions only

4. **Graceful Degradation**: The LSP server must handle incomplete/malformed YAML gracefully (common during editing). Use try/except with regex fallbacks where appropriate.

### Implementation Guidelines

**Adding New Completion Features:**

When adding a new completion prefix (e.g., `env.*`, `dep.*`, `self.*`):

1. **Parser Wrapper First**: Add extraction function to `parser_wrapper.py` (e.g., `extract_env_vars(text)`)
   - Unit test the extraction with valid YAML
   - Unit test with invalid YAML (should return empty list)
   - Include regex fallback if needed for incomplete YAML

2. **Position Detection (if context-aware)**: Add position detection to `position_utils.py` if needed
   - Unit test position detection with various YAML structures
   - Handle edge cases (multiline fields, nested blocks, etc.)

3. **Server Completion Logic**: Add completion handler to `server.py`
   - Reuse `_complete_template_variables()` helper function
   - Unit test completion filtering and context awareness
   - Unit test empty/missing identifier cases

4. **Integration Tests**: Add integration test to `tests/integration/test_lsp_completion.py`
   - Test full workflow: initialize → open → complete
   - Test document changes triggering re-parse
   - Test context awareness (if applicable)

5. **E2E Tests**: Add subprocess test to `tests/e2e/test_lsp_subprocess.py`
   - Test LSP protocol over stdio
   - Verify JSON-RPC request/response format

**Testing Strategy:**

- **Unit tests** should be the primary testing approach (fastest, most focused)
- **Integration tests** cover full LSP workflows across modules
- **E2E tests** verify subprocess execution and protocol compliance (slower, fewer tests)

**What NOT to Do:**

- DO NOT reimplement tasktree's parser or variable extraction logic
- DO NOT add completion logic directly to parser modules (keep separation of concerns)
- DO NOT skip unit tests in favor of integration/e2e tests
- DO NOT add features without comprehensive test coverage

### Current LSP Feature Status

**Implemented:**
- ✅ Server lifecycle (initialize, shutdown, exit)
- ✅ Document management (textDocument/didOpen, textDocument/didChange)
- ✅ `tt.*` completion - Built-in variables (8 variables from executor.py)
- ✅ `var.*` completion - User-defined variables (from variables section)
- ✅ `arg.*` completion - Task arguments (context-aware, scoped to current task)
- ✅ `env.*` completion - Environment variables (from current process env, sorted alphabetically, no scoping)
- ✅ `self.inputs.*` completion - Named task inputs (task-scoped, named only)
- ✅ `self.outputs.*` completion - Named task outputs (task-scoped, named only)
- ✅ Task name completion in `deps` lists - with self-exclusion and import-aware namespacing

**Not Yet Implemented:**
- ❌ `dep.*.outputs.*` completion - Dependency outputs
- ❌ Diagnostics (undefined variables, circular deps, etc.)
- ❌ Go-to-definition for task references
- ❌ Hover documentation for variables/tasks

### Common Patterns

**Extracting Identifiers from YAML:**

```python
def extract_identifiers(text: str) -> list[str]:
    """Extract identifiers from tasktree YAML text."""
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return []

        # Extract identifiers...
        return sorted(identifier_list)
    except (yaml.YAMLError, AttributeError) as e:
        logger.debug(f"YAML parse failed: {e}")
        # Optional: Add regex fallback for incomplete YAML
        return []
```

**Reusing Completion Logic:**

The `_complete_template_variables()` helper function in `server.py` handles:
- Prefix matching (`{{ prefix.`)
- Template boundary detection (no completions after `}}`)
- Partial filtering (e.g., `{{ var.my` → only variables starting with "my")
- CompletionItem creation with appropriate detail/kind

Reuse this function for all new completion prefixes - DO NOT duplicate the logic.

### LSP Testing Examples

**Unit Test Pattern:**
```python
def test_extract_something_from_yaml(self):
    """Test extracting something from valid YAML."""
    yaml_text = "...\n"
    result = extract_something(yaml_text)
    self.assertEqual(result, ["expected", "items"])
```

**Integration Test Pattern:**
```python
def test_complete_prefix_after_document_change(self):
    """Test completion updates after document changes."""
    server = create_server()
    server.handlers["initialize"](InitializeParams(...))
    server.handlers["textDocument/didOpen"](...)
    result = server.handlers["textDocument/completion"](...)
    # Change document
    server.handlers["textDocument/didChange"](...)
    result2 = server.handlers["textDocument/completion"](...)
    # Assert result2 reflects changes
```

For complete LSP documentation, see `src/tasktree/lsp/README.md`.