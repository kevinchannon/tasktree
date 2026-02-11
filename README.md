# Task Tree (tt) - Developer Guide

[![Tests](https://github.com/kevinchannon/task-tree/actions/workflows/test.yml/badge.svg)](https://github.com/kevinchannon/task-tree/actions/workflows/test.yml)

A task automation tool that combines simple command execution with dependency tracking and incremental execution.

## What is Task Tree?

Task Tree allows you to define your project's build, test, and deployment workflows in a single YAML file with automatic incremental execution, dependency tracking, and rich parameterization.

**Example `tasktree.yaml`:**

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

Run your workflow:
```bash
tt test  # Runs build → package → test, skipping unchanged steps
```

**For complete user documentation, see [User Guide](src/tasktree/README.md).**

## Project Structure

```
tasktree/
├── src/tasktree/           # Main source code
│   ├── cli.py              # CLI interface (Typer)
│   ├── parser.py           # YAML recipe parsing
│   ├── executor.py         # Task execution engine
│   ├── graph.py            # Dependency resolution
│   ├── docker.py           # Docker integration
│   ├── substitution.py     # Template variable engine
│   ├── state.py            # State file management
│   ├── hasher.py           # Task hashing for caching
│   └── types.py            # Custom Click parameter types
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── e2e/                # End-to-end tests
├── schema/                 # JSON Schema for YAML validation
├── pyproject.toml          # Project configuration
└── tasktree.yaml           # Development task definitions
```

## Technology Stack

- **Python 3.11+** - Core language requirement
- **PyYAML** - YAML parsing
- **Typer + Click + Rich** - CLI framework with rich terminal output
- **graphlib.TopologicalSorter** - Dependency graph resolution
- **pathlib + pathspec** - File operations and glob expansion
- **docker (Python SDK)** - Docker integration
- **platformdirs** - Cross-platform config paths

## Development Setup

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended)

### Initial Setup

```bash
# Clone repository
git clone https://github.com/kevinchannon/task-tree.git
cd tasktree

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv run tt dev-setup
```

## Development Workflow

In order to test with the actual changes you're making, and not an installed version of tasktree, invoke `tt` as `uv run tt <task>`. This will use the repo version of the `tt` code, and not the installed version. For other projects on your machine that may use `tt` for things, then continue to just invoke directly, as normal. 

### Test Organization

- **Unit tests** (`tests/unit/`): Test individual functions and classes in isolation
- **Integration tests** (`tests/integration/`): Test interactions between modules using CliRunner
- **E2E tests** (`tests/e2e/`): Full subprocess execution and Docker container tests

### Using Task Tree for Development

The repository includes a `tasktree.yaml` with development tasks:

```bash
uv run tt test          # Run tests
uv run tt coverage      # Run tests with coverage
uv run tt build         # Build wheel package
uv run tt install-dev   # Install package in development mode
uv run tt clean         # Remove build artifacts
```

## Code Style and Architecture

### Key Principles

- **SOLID principles**: Single responsibility, open/closed, Liskov substitution, interface segregation, dependency inversion
- **Clean Code practices**: Meaningful names, small functions, minimal comments (code should be self-documenting)
- **DRY (Don't Repeat Yourself)**: Abstract common patterns into reusable functions
- **Type hints**: Use Python type hints throughout for better IDE support and documentation

### Development Philosophy

- **Small, incremental changes**: Each commit should contain a small, focused change with accompanying tests
- **Test-driven development**: Write tests first or alongside implementation
- **No skipped tests**: Use `unittest.skipUnless` only for platform-specific cases (never `unittest.skip`)
- **Efficient token usage**: Minimize AI token consumption by reading only necessary files

### Code Organization

- Keep functions small and focused
- Use descriptive names for functions and variables
- Abstract algorithmic logic from types (follow Liskov Substitution Principle)
- Prefer small named functions over inline comments

## Implementation Notes

### State Management

- State stored in `.tasktree-state` JSON file at project root
- Tasks identified by hash of their definition (command, outputs, working_dir, args, runner)
- State tracks task execution timestamp and input file timestamps
- Automatic cleanup of stale state entries

### Incremental Execution

A task runs if:
- Task definition changed (hash mismatch)
- Input files modified since last run
- Dependencies re-executed
- Never executed before
- No inputs defined (always runs)
- Runner changed (CLI override or config change)

### Docker Integration

- Builds images from Dockerfiles
- Mounts state file at `/tasktree-internal/.tasktree-state`
- User mapping (run as host UID:GID by default)
- Volume mounts and port mappings
- Build arguments and environment variables
- Nested task invocations with runner compatibility checks
- Cross-platform support: Linux and Windows containers with appropriate script execution (`.sh`, `.bat`, `.ps1`)

### Template Substitution

Variables resolved in this order:
1. Variables section (`{{ var.name }}`)
2. Dependency outputs (`{{ dep.task.outputs.name }}`)
3. Self-references (`{{ self.inputs.name }}`, `{{ self.outputs.name }}`)
4. Task arguments (`{{ arg.name }}`)
5. Environment variables (`{{ env.NAME }}`)
6. Built-in variables (`{{ tt.project_root }}`, etc.)

## Testing Best Practices

### Writing Unit Tests

- Use `unittest.mock` for external dependencies
- Test one function/method per test case
- Use descriptive test names: `test_<what>_<scenario>_<expected_result>`
- Mock subprocess calls, file I/O, and Docker operations

### Writing Integration Tests

- Use `click.testing.CliRunner` for CLI testing
- Create temporary directories for test artifacts
- Clean up test resources in teardown methods
- Test interactions between multiple modules

### Writing E2E Tests

- Test full subprocess execution
- Test Docker container workflows
- Use real filesystem and state files in temp directories
- Verify actual command output and exit codes

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make small, incremental commits with tests
4. Run the full test suite: `uv run pytest`
5. Push to your fork: `git push origin feature/my-feature`
6. Create a Pull Request

## Releasing

New releases are created by pushing version tags to GitHub. The release workflow automatically builds and publishes to PyPI.

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
   - PyPI: https://pypi.org/project/tasktree/
   - Test: `pipx install --force tasktree`

### Version Numbering

Follow semantic versioning:
- `v1.0.0` - Major release (breaking changes)
- `v1.1.0` - Minor release (new features, backward compatible)
- `v1.1.1` - Patch release (bug fixes)

## License

See [LICENSE](LICENSE) file for details.

## Links

- **User Documentation**: [User Guide](src/tasktree/README.md)
- **GitHub Repository**: https://github.com/kevinchannon/task-tree
- **Issue Tracker**: https://github.com/kevinchannon/task-tree/issues
- **PyPI Package**: https://pypi.org/project/tasktree/
