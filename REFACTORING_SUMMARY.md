# Environment → Runner Refactoring Summary

## Overview

This document summarizes the systematic refactoring to rename execution environments to "runners" throughout the TaskTree codebase.

## Refactoring Map

### Core Terminology Changes

| Old Term | New Term | Context |
|----------|----------|---------|
| `Environment` | `Runner` | Class name |
| `environments` | `runners` | YAML section, dict fields |
| `env` | `run_in` | Task field in YAML and Python |
| `get_environment()` | `get_runner()` | Method name |
| `hash_environment_definition()` | `hash_runner_definition()` | Function name |
| `is_docker_environment()` | `is_docker_runner()` | Function name |
| `_substitute_builtin_in_environment()` | `_substitute_builtin_in_runner()` | Method name |

### **IMPORTANT**: What NOT to Change

**Preserve** all references to "environment variable" - these refer to shell/OS environment variables and should remain unchanged.

## Files Modified

### ✅ Source Code (Complete)

1. **src/tasktree/parser.py**
   - Class: `Environment` → `Runner`
   - Field: `Task.env` → `Task.run_in`
   - Field: `Recipe.environments` → `Recipe.runners`
   - Method: `get_environment()` → `get_runner()`
   - YAML keys: `"environments"` → `"runners"`, `"env"` → `"run_in"`

2. **src/tasktree/executor.py**
   - Import: `Environment` → `Runner`
   - All method signatures and type hints updated
   - Method: `_substitute_builtin_in_environment()` → `_substitute_builtin_in_runner()`

3. **src/tasktree/hasher.py**
   - Function: `hash_environment_definition()` → `hash_runner_definition()`

4. **src/tasktree/cli.py**
   - Method calls and error messages updated

5. **src/tasktree/graph.py**
   - Task field access: `task.env` → `task.run_in`
   - Method calls updated

6. **src/tasktree/docker.py**
   - Import and type hints updated
   - Function: `is_docker_environment()` → `is_docker_runner()`

### 🔄 Remaining (Use `complete_refactoring.py`)

#### Test Files (~50 files)
- `tests/unit/test_parser.py` - Core parser tests
- `tests/unit/test_executor.py` - Executor tests
- `tests/unit/test_docker.py` - Docker tests
- `tests/unit/test_environment_tracking.py` - Runner tracking tests
- `tests/integration/test_*.py` - All integration tests
- `tests/e2e/test_docker_*.py` - End-to-end Docker tests

#### Documentation Files
- `README.md` - Main documentation
- `CLAUDE.md` - Project guidelines
- `schema/README.md` - Schema documentation

#### Schema Files
- `schema/tasktree-schema.json` - JSON schema definition

## YAML Schema Changes

### Old Format
```yaml
environments:
  default: builder

  builder:
    shell: bash
    preamble: set -euo pipefail

  docker-env:
    dockerfile: Dockerfile
    context: .

tasks:
  build:
    env: builder
    cmd: cargo build
```

### New Format
```yaml
runners:
  default: builder

  builder:
    shell: bash
    preamble: set -euo pipefail

  docker-runner:
    dockerfile: Dockerfile
    context: .

tasks:
  build:
    run_in: builder
    cmd: cargo build
```

## Running the Refactoring

### Step 1: Source Code (Complete ✅)
The core source code has been refactored manually with careful attention to:
- Type safety
- Method signatures
- Import statements
- Docstrings and comments

### Step 2: Tests and Documentation
Run the provided script:

```bash
cd /home/runner/work/tasktree/tasktree
python3 complete_refactoring.py
```

This will:
1. Update all test files (*.py in tests/)
2. Update all documentation (README.md, CLAUDE.md, etc.)
3. Update the JSON schema
4. Preserve "environment variable" references

### Step 3: Validation
```bash
# Run the test suite
pytest tests/

# Check for any remaining references
grep -r "\.env\b" src/ tests/ --include="*.py" | grep -v "environment variable"
grep -r "environments:" . --include="*.yaml" --include="*.md"
```

### Step 4: Commit
```bash
git add -A
git commit -m "Complete environment → runner refactoring

- Renamed Environment class to Runner
- Changed YAML section from 'environments' to 'runners'
- Changed task field from 'env' to 'run_in'
- Updated all method names and function signatures
- Updated tests and documentation
- Preserved 'environment variable' terminology"
```

## Testing Strategy

After refactoring, ensure:

1. **Unit tests pass**: `pytest tests/unit/`
2. **Integration tests pass**: `pytest tests/integration/`
3. **E2E tests pass**: `pytest tests/e2e/`
4. **Docker tests work**: Specifically test Docker runner functionality
5. **CLI still works**: Test with actual YAML files

## Rollback Plan

If issues arise:
```bash
git revert HEAD
```

The refactoring is designed to be atomic - all changes are in a single commit (or series of small commits) that can be reverted cleanly.

## Notes

- This is a **breaking change** for users - existing `tasktree.yaml` files will need updating
- Consider a deprecation warning in a future version that supports both syntaxes
- Update migration guide in documentation
- Consider tooling to auto-migrate user configs

## Rationale

The refactoring improves clarity by:
1. Distinguishing execution runners from environment variables
2. Using more accurate terminology ("runner" vs "environment")
3. Making the API more intuitive for new users
4. Aligning with industry terminology (GitHub Actions uses "runners")
