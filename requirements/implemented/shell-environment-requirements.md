# Task Tree Shell Environment Requirements

## Overview

This document describes the shell environment execution strategy for Task Tree, including multi-line command handling, configurable shell environments, and platform-specific behaviour.

## Problem Statement

Task Tree currently executes commands using `subprocess.run()` with `shell=True`, passing command strings directly to the shell. This approach has several limitations:

1. **Multi-line fragility**: Joining lines with `\n` breaks shell line continuations and complex syntax
2. **Platform ambiguity**: Windows has no sensible default (cmd.exe vs PowerShell have incompatible syntax)
3. **Limited configurability**: No way to set shell options like `set -euo pipefail` for all tasks
4. **Shebang limitations**: Can't leverage shebangs for alternative interpreters (Python, Perl, etc.)

## Core Requirements

### 1. Multi-line Command Execution

**All multi-line commands must be written to temporary script files:**

- Create temporary file with appropriate extension (`.sh`, `.ps1`, `.py`, etc.)
- Write command content to file
- Set execute permissions (Unix/macOS only)
- Execute file directly (not through shell string)
- Automatic cleanup via Python's `tempfile` module

**Benefits:**
- Shell parses the file correctly (handles line continuations, here-docs, etc.)
- Consistent behaviour across platforms
- Supports arbitrary interpreters via shebangs (Unix) or explicit invocation (Windows)

**Single-line commands:**
- Continue using direct shell invocation for simplicity
- Use configured shell with appropriate invocation args

### 2. Environment Configuration

Add an `environments` section to `tasktree.yaml`:

```yaml
environments:
  default: bash-strict
  
  bash-strict:
    shell: bash
    args: ['-c']              # For single-line: bash -c "command"
    preamble: |               # For multi-line: prepended to script
      set -euo pipefail
  
  powershell:
    shell: powershell
    args: ['-ExecutionPolicy', 'Bypass', '-Command']
    preamble: |
      $ErrorActionPreference = 'Stop'
  
  cmd:
    shell: cmd
    args: ['/c']
  
  python:
    shell: python
    args: ['-c']

tasks:
  build:
    # Uses 'default' environment (bash-strict)
    cmd: |
      cargo build --release
      cp target/release/bin dist/
  
  windows-task:
    env: powershell
    cmd: |
      Compress-Archive -Path dist/* -DestinationPath package.zip
```

**Environment fields:**
- `shell`: Path or name of shell/interpreter executable
- `args`: Arguments for single-line command invocation
- `preamble`: Text prepended to multi-line scripts (optional)

**Task-level override:**
- `env` field in task definition overrides default environment
- If not specified, uses environment named `default` from environments section

### 3. Platform-Specific Defaults

**When no `environments` section exists:**

**Unix/Linux/macOS:**
```yaml
# Implicit default
bash-strict:
  shell: bash
  args: ['-c']
  preamble: |
    set -euo pipefail
```

**Windows:**
- No default for multi-line commands (error with helpful message)
- Single-line commands use `cmd.exe`
- Error message: "Multi-line commands on Windows require explicit 'env' field. Supported: 'cmd', 'powershell', 'python', 'bash' (WSL)"

### 4. Shebang Handling

**Unix/Linux/macOS:**
- Honour all shebangs in multi-line commands
- Standard Unix behaviour: kernel's execve() interprets shebang
- If no shebang present, prepend shebang based on environment shell

**Windows:**
- **Python shebangs**: Parse and handle explicitly
  - Recognize: `#!/usr/bin/env python`, `#!/usr/bin/env python3`, `#!/usr/bin/python`, `#!/usr/bin/python3`
  - Extract script body (lines after shebang)
  - Write to temp file with `.py` extension
  - Invoke: `python <tempfile>`
- **Other shebangs**: Error with suggestion to use WSL or explicit `env` field
- **No shebang**: Use `env` field to determine execution method

### 5. Command-Line Override

Add global option to override environment for all tasks:

```bash
tt --env=powershell build 
tt -e python build
```

**Behaviour:**
- Overrides both default environment and task-specific `env` fields
- Useful for testing tasks in different shells
- Useful for cross-platform task files where different users need different defaults

### 6. Task Hashing

**Include environment configuration in task hash:**

**Rationale:**
- Different shells/flags = different execution semantics
- Changing environment should invalidate cache
- Prevents incorrect cache hits when execution method changes

## Testing Requirements

### Unit Tests

1. **Single-line execution**: Verify shell invocation with correct args
2. **Multi-line execution**: Verify temp file creation and cleanup
3. **Shebang parsing**: Unix and Windows paths
4. **Environment resolution**: default → task → CLI override priority
5. **Task hashing**: Verify environment config included in hash
6. **Platform detection**: Mock platform.system() for cross-platform tests

### Integration Tests

1. **Unix shebang support**: Python, Perl, Ruby, Node.js scripts
2. **Windows Python shebangs**: Various formats
3. **Environment preamble**: Verify bash strict mode catches errors
4. **CLI override**: Verify --env flag overrides config
5. **Error cases**: Invalid shebangs, missing shells, Windows multi-line without env

## Documentation Requirements

### User Guide Sections

**"Execution Environments":**
- Explain shell configuration
- Show example environment definitions
- Explain single-line vs multi-line behaviour
- Platform-specific guidance

**"Multi-line Commands":**
- Explain temp file execution
- Show shebang usage (Unix)
- Show env field usage (Windows)
- Common patterns (bash scripts, Python scripts, PowerShell)

**"Command-Line Reference":**
- Document `--env` / `-e` flag
- Show override examples

### Example Configurations

```yaml
# Cross-platform Python task
analyze:
  cmd: |
    #!/usr/bin/env python3
    import sys
    print(f"Python version: {sys.version}")
    # ... analysis code ...

# Platform-specific tasks
build-unix:
  cmd: |
    cargo build --release
    strip target/release/bin

build-windows:
  env: powershell
  cmd: |
    cargo build --release
    # PowerShell-specific post-processing

# Custom strict shell
environments:
  default: extra-strict
  
  extra-strict:
    shell: bash
    args: ['-c']
    preamble: |
      set -euxo pipefail
      export LANG=C
```

## Import Behavior

When importing task files that contain `environments` sections, both environments and tasks are namespaced to maintain isolation and prevent naming conflicts.

### Environment Namespacing

**Environments from imported files are namespaced:**

```yaml
# shared/utils.yaml
environments:
  default: python
  python:
    shell: python
  custom-bash:
    shell: bash
    preamble: set -x

tasks:
  task-a:
    # No env - uses file's default
    cmd: print("a")
  
  task-b:
    env: custom-bash
    cmd: echo "b"
  
  task-c:
    # No env, no file default
    cmd: echo "c"
```

```yaml
# Root tasktree.yaml
import:
  utils: shared/utils.yaml

environments:
  default: bash-strict
  bash-strict:
    shell: bash
    preamble: set -euo pipefail

tasks:
  main:
    deps: [utils.task-a]
    cmd: echo "done"
  
  other:
    env: utils.python  # Can reference imported environment
    cmd: python analyze.py
```

**After import resolution (in-memory representation):**
- `utils.python` environment available
- `utils.custom-bash` environment available
- `utils.task-a` gets `env: utils.python` (file's default, namespaced)
- `utils.task-b` gets `env: utils.custom-bash` (explicit ref, namespaced)
- `utils.task-c` has no env (file had no default) - will use global default
- `main` gets `env: bash-strict` (root file's default)
- `other` has `env: utils.python` (explicit reference to imported environment)

### Environment Resolution Algorithm

**Three-level resolution for task environments:**

1. **Explicit env in task**: Use it (with namespace rewriting for imported tasks)
2. **File-level default**: If task has no env but file defines `default`, use file's default
3. **Global platform default**: If no env and no file default, use global default at execution

### Key Principles

**Self-contained imports:**
- Imported files should be self-contained with their own environments
- Environment references in imported tasks must resolve within that file (after namespacing)
- Imported tasks cannot directly reference root file environments in YAML
- This maintains unidirectional dependency: root → imported

**Behavior preservation:**
- A task's behavior should not change based on which file imports it
- File-level defaults are resolved during import and frozen into the task definition
- Tasks without env and without file default consistently use global platform default

**Scope of defaults:**
- Root file's `default` applies only to tasks in the root file
- Imported file's `default` applies only to tasks in that imported file
- Tasks with no env (after resolution) use global platform default

### Examples

**Example 1: Imported file with default**
```yaml
# utils.yaml
environments:
  default: python
  python:
    shell: python

tasks:
  setup:
    cmd: print("setup")  # Will use python (file default)
```

After import as `utils`:
- `utils.setup` has `env: utils.python`

**Example 2: Imported file without default**
```yaml
# scripts.yaml
environments:
  node:
    shell: node

tasks:
  build:
    env: node
    cmd: console.log("build")
  
  test:
    cmd: echo "test"  # No env, file has no default
```

After import as `scripts`:
- `scripts.build` has `env: scripts.node`
- `scripts.test` has no env → uses global platform default (bash on Unix)

**Example 3: Root file references imported environment**
```yaml
# Root file
import:
  utils: shared/utils.yaml

tasks:
  analyze:
    env: utils.python  # Valid - references imported environment
    cmd: python analyze.py
```

**Example 4: Cannot cross-reference (invalid)**
```yaml
# utils.yaml - INVALID
tasks:
  task-a:
    env: bash-strict  # Error if bash-strict not in utils.yaml
    cmd: echo "a"
```

This would error unless `bash-strict` is defined in utils.yaml itself. Tasks in imported files cannot reference root environments directly in YAML.

## Migration Path

**For existing tasktree.yaml files:**
- No changes required for single-line commands
- Multi-line commands on Unix: automatic bash wrapping (same as before)
- Multi-line commands on Windows: will error with helpful migration message

**Recommended migration:**
1. Add `environments` section with sensible defaults
2. Add `env` field to Windows-specific tasks
3. Consider adding shebangs to Python/scripting tasks for portability

**For files that will be imported:**
- Define `default` environment if tasks should have consistent behavior
- Include all necessary environments within the file (self-contained)
- Cannot rely on importing file's environments

## Future Enhancements

**Potential additions (not required for initial implementation):**
- Environment variable passing: `env_vars: {VAR: value}`
- Conditional environments: `env: "{{ 'powershell' if windows else 'bash' }}"`
- Shell detection: Auto-detect available shells and warn if configured shell missing
- Verbose mode: Show which environment/shell is being used for each task
- Environment aliases: `aliases: [ps, pwsh]` for `powershell` environment