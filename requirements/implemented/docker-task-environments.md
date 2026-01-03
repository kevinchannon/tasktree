# Docker Environment Support - Implementation Requirements

## Overview

Add support for running tasks inside Docker containers defined in `tasktree.yaml`. This allows isolated build/test environments without external wrapper scripts, replacing the current pattern of `run-in-docker.sh tt build` with native Docker integration.

## Motivation

Users currently maintain separate wrapper scripts to run `tt` inside Docker containers. This creates duplication and makes the build environment implicit rather than declarative. By adding first-class Docker support, the complete build environment becomes part of the task definition and benefits from `tt`'s dependency tracking and caching.

## Core Requirements

### 1. Environment Definition Syntax

Tasks can reference named environments that specify Docker containers:

```yaml
environments:
  builder:
    dockerfile: ./Dockerfile.build
    context: ./docker-context/
    volumes:
      - ./:/workspace
      - ~/.cargo:/root/.cargo
    working_dir: /workspace

  tester:
    dockerfile: ./Dockerfile.test
    context: .
    volumes:
      - ./:/workspace
    working_dir: /workspace/tests

tasks:
  build:
    env: builder
    outputs: [target/release/myapp]
    cmd: cargo build --release

  test:
    env: tester
    deps: [build]
    cmd: pytest .
```

**Environment Fields:**
- `dockerfile`: Path to Dockerfile (required)
- `context`: Path to build context directory (required)
- `volumes`: List of volume mounts in Docker `-v` format (optional, default: none)
- `ports`: List of port mappings into the container
- `env_vars`: List of environment variables and their values that should exist inside the running container
- `working_dir`: Working directory inside container (optional, default: /)
- Translations of other common "docker run" options, such as TTY settings, interactive running, etc 

**Path Resolution:**
All paths in environment specs (dockerfile, context, volume sources) are resolved relative to the location of `tasktree.yaml`, consistent with how task paths are resolved.

#### Command line overrides

The task environment should be overridable on the command line, with a `--env` (or `-e`) argument to `tt`. So, if the `tasktree.yaml` contains an environment named "builder", then it should be possible to invoke, for example, a "build-all" task in `tt` like:
```shell
tt -e builder build-all
```
Or,
```shell
tt --env=builder build-all
```

### 2. Task Environment Reference

Tasks reference environments via the `env` field:

```yaml
tasks:
  my-task:
    env: builder  # References environments.builder
    cmd: make all
```

Tasks without `env` field run directly on the host (existing behavior).

### 3. Implicit Input Tracking

When a task uses `env: <name>`, the following automatically become implicit inputs to that task (in addition to normal input inheritance from dependencies):

1. **Dockerfile**: The file specified in `dockerfile` field
2. **.dockerignore**: If present in the context directory
3. **Context files**: All files in the context directory, respecting `.dockerignore` rules
4. **Pinned base images**: Digests from `FROM` lines that use `@sha256:...` syntax

These implicit inputs mean:
- Changes to any of these files/directories trigger task re-execution
- These inputs participate in staleness detection during planning phase
- They are tracked in the state file like any other input

### 4. Change Detection Strategy

#### Dockerfile and .dockerignore

Standard file tracking via mtime:
- Store mtime in state file
- Compare mtime on next run
- If newer, task is stale

#### Context Directory

Efficiently detect if any file in context changed:

```python
def context_changed_since(context_path, dockerignore_path, last_run_time):
    """
    Check if any file in context has changed since last_run_time.
    Early-exit on first changed file found.
    
    Returns: bool
    """
    dockerignore_rules = parse_dockerignore(dockerignore_path)
    
    for file_path in context_path.rglob('*'):
        if file_path.is_file():
            if dockerignore_rules.matches(file_path):
                continue
            if file_path.stat().st_mtime > last_run_time:
                return True  # Found change, exit early
    
    return False  # No changes found
```

**Key points:**
- Walk entire context tree
- Skip files matching `.dockerignore` patterns
- Early exit on first changed file (optimization)
- Only check mtime, don't hash contents
- Store the check result timestamp in state file

**Performance considerations:**
- For small contexts (<1000 files): negligible overhead
- For large contexts: still O(n) worst case, but early exit helps
- Consider caching context check result per environment per `tt` invocation (multiple tasks using same env)

#### Base Image Tracking

Parse `FROM` lines in Dockerfile to extract base image references:

**Pinned (digest-based):**
```dockerfile
FROM rust:1.75@sha256:abc123def456...
```
- Extract the digest: `sha256:abc123def456...`
- Store in state file as `_digest_sha256:abc123def456`
- If digest in Dockerfile changes, task is stale
- This is trackable and deterministic

**Unpinned (tag-based):**
```dockerfile
FROM rust:1.75
FROM python:3.11-slim
```
- Issue warning to user
- Do NOT track as input (cannot reliably detect updates)
- Recommend user either:
  - Pin to digest for reproducibility
  - Run with `--force` flag if concerned about stale base images

**Warning message format:**
```
Warning: Dockerfile.build uses unpinned base image(s):
  - rust:1.75
  - python:3.11-slim

Task Tree cannot detect if these base images have been updated on the registry.
For reproducible builds, pin to digests:
  FROM rust:1.75@sha256:abc123...

Alternatively, run 'tt --force <task>' to force rebuild with latest images.
```

**Multi-stage builds:**
```dockerfile
FROM rust:1.75@sha256:abc123... AS builder
FROM debian:slim
```
Parse ALL `FROM` lines, not just first. Check each for pinning. Issue separate warnings for each unpinned image.

**ARG-based FROM:**
```dockerfile
ARG BASE_IMAGE=rust:1.75
FROM ${BASE_IMAGE}
```
Cannot reliably parse. Treat as unpinned, issue warning mentioning variable substitution makes tracking impossible.

### 5. Execution Flow

#### Planning Phase (Dry-Run Safe)

For each task with `env: <name>`:

1. Resolve environment definition
2. Check if Dockerfile changed (mtime)
3. Check if .dockerignore changed (mtime) 
4. Check if context directory changed (walk with early exit)
5. Parse FROM lines, check if pinned digests changed
6. Determine if task is stale based on above + normal input tracking

**Critical:** This phase must NOT execute `docker build`. Must be fast (suitable for `--dry-run`).

**Output for dry-run:**
```
Would run: build
  Reason: docker-context/requirements.txt changed (mtime: 1734567890 > last_run: 1734567800)
  Would rebuild Docker image from Dockerfile.build

Would run: test  
  Reason: dependency 'build' needs to run
  Would use cached Docker image (no environment changes)
```

#### Execution Phase

For each task determined to need running:

1. Build Docker image:
   ```bash
   docker build -t tt-env-<envname> -f <dockerfile> <context>
   ```

2. Execute task command in container:
   ```bash
   docker run --rm \
     -v <volume1> \
     -v <volume2> \
     -w <working_dir> \
     tt-env-<envname> \
     sh -c "<cmd>"
   ```

3. Update state file with new timestamps and digests

**Image naming:** Use `tt-env-<envname>` where `<envname>` is the key from `environments:` section. This makes images:
- Identifiable in `docker images` output
- Debuggable via `docker run -it tt-env-builder bash`
- Cleanable via `docker image prune`

**Command execution:** Always wrap in `sh -c` to handle multi-line commands and shell features (pipes, redirects, etc.).

**Error handling:**
- If `docker build` fails: fail task, propagate error
- If `docker run` fails: fail task, propagate error  
- If Dockerfile not found: fail immediately with clear message
- If context directory not found: fail immediately with clear message

### 6. Task Hashing

The task hash must include the environment specification to ensure changes to environment config invalidate cached task results:

```python
def compute_task_hash(task_def, env_spec=None):
    hash_inputs = {
        'cmd': task_def['cmd'],
        'outputs': task_def.get('outputs', []),
        'working_dir': task_def.get('working_dir', ''),
    }
    
    if env_spec:
        hash_inputs['env'] = {
            'dockerfile': env_spec['dockerfile'],
            'context': env_spec['context'],
            'volumes': env_spec.get('volumes', []),
            'working_dir': env_spec.get('working_dir', '/'),
        }
    
    return hashlib.sha256(
        json.dumps(hash_inputs, sort_keys=True).encode()
    ).hexdigest()[:8]
```

**What's included:** Structural environment definition (paths, volumes, etc.)

**What's excluded:** Contents of Dockerfile and context files (tracked separately as inputs)

**Effect:** Changing environment spec invalidates task hash, causing task to re-execute even if source files unchanged.

### 7. Working Directory Resolution

Task's `working_dir` interacts with environment's `working_dir` and volumes:

**Scenario 1: Task specifies working_dir**
```yaml
environments:
  builder:
    volumes: [./:/workspace]
    working_dir: /workspace

tasks:
  build:
    env: builder
    working_dir: src/
    cmd: make
```
**Resolution:** Container working dir = `/workspace/src/`
Task's `working_dir` is relative to environment's mount point.

**Scenario 2: Task doesn't specify working_dir**
```yaml
environments:
  builder:
    volumes: [./:/workspace]
    working_dir: /workspace

tasks:
  build:
    env: builder
    cmd: make
```
**Resolution:** Container working dir = `/workspace`
Use environment's `working_dir` directly.

**Scenario 3: Neither specifies working_dir**
```yaml
environments:
  builder:
    volumes: [./:/workspace]

tasks:
  build:
    env: builder
    cmd: make
```
**Resolution:** Container working dir = `/` (Docker default)

**Implementation:**
```python
def resolve_working_dir(task_def, env_spec):
    env_workdir = env_spec.get('working_dir', '/')
    task_workdir = task_def.get('working_dir', '')
    
    if task_workdir:
        # Task workdir is relative to env workdir
        return os.path.join(env_workdir, task_workdir)
    else:
        return env_workdir
```

### 8. State File Schema Extension

Extend existing state file to track environment-related information:

```json
{
  "a3f5c2b1": {
    "last_run": 1734567890,
    "input_state": {
      "Dockerfile.build": 1734567880,
      ".dockerignore": 1734560000,
      "_context_docker-context": 1734567885,
      "_digest_sha256:abc123def456": 1734567880,
      "src/main.rs": 1734567870,
      "Cargo.toml": 1734560000
    }
  }
}
```

**Special key prefixes:**
- `_context_<path>`: Result timestamp from checking that context directory
- `_digest_<hash>`: Pinned base image digest from FROM line

**Reasoning:**
- Keeps all tracking in single state file
- Special prefixes distinguish environment inputs from regular file inputs
- Context result timestamp allows skipping re-walk if context itself hasn't been modified
- Digest tracking enables detection of Dockerfile base image changes

### 9. .dockerignore Parsing

Must correctly parse and apply `.dockerignore` syntax during context change detection.

**Supported syntax:**
- Comments: `# This is a comment`
- Patterns: `*.pyc`, `__pycache__/`, `**/*.tmp`
- Negation: `!important.pyc` (include despite earlier exclusion)
- Directory markers: `node_modules/` (trailing slash)

**Implementation recommendation:**
Use Python's `pathspec` library rather than implementing from scratch:

```python
import pathspec

def parse_dockerignore(dockerignore_path):
    """Parse .dockerignore file into pathspec matcher."""
    if not dockerignore_path.exists():
        return pathspec.PathSpec([])  # Empty matcher
    
    with open(dockerignore_path) as f:
        spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
    
    return spec

def matches_ignore(file_path, context_path, spec):
    """Check if file_path matches .dockerignore patterns."""
    relative_path = file_path.relative_to(context_path)
    return spec.match_file(str(relative_path))
```

**Edge cases:**
- Missing `.dockerignore`: treat as empty (no files ignored)
- Empty `.dockerignore`: no files ignored
- Invalid patterns: log warning, skip invalid pattern, continue

## Acceptance Criteria

### Basic Functionality
- [ ] Task with `env: builder` executes inside specified Docker container
- [ ] Volume mounts work correctly (files written in container visible on host)
- [ ] Multiple volume mounts work correctly
- [ ] Task `working_dir` resolves correctly relative to environment mount point
- [ ] Commands with pipes, redirects, and multi-line syntax work correctly
- [ ] Task outputs written in container are detected as changed by dependent tasks

### Incremental Behavior  
- [ ] Task reruns when Dockerfile changes
- [ ] Task reruns when .dockerignore changes
- [ ] Task reruns when any file in context changes (respecting .dockerignore)
- [ ] Task does NOT rerun when only Docker layer cache handles Dockerfile comment changes
- [ ] Task does NOT rerun when ignored files in context change
- [ ] Early exit from context walk when first changed file found (performance)

### Base Image Handling
- [ ] `FROM rust@sha256:abc123...` is tracked as input
- [ ] Changing pinned digest triggers task rerun  
- [ ] `FROM rust:1.75` (unpinned) shows warning message
- [ ] Warning explains that base image updates won't be detected
- [ ] Warning suggests pinning to digest or using `--force`
- [ ] Multi-stage builds check all FROM lines
- [ ] ARG-based FROM lines show appropriate warning

### Dry-Run Support
- [ ] `tt --dry-run <task>` shows which tasks would run
- [ ] Dry-run does NOT execute `docker build`
- [ ] Dry-run does NOT execute `docker run`  
- [ ] Dry-run reports why each task would run (file changed, dependency changed, etc.)
- [ ] Dry-run mentions if Docker image would be rebuilt
- [ ] Dry-run is fast (< 2 seconds for typical project)

### Error Handling
- [ ] Missing Dockerfile fails with clear error message and path
- [ ] Missing context directory fails with clear error message
- [ ] Invalid Dockerfile fails with clear error showing Docker's error
- [ ] Docker build failure fails task with clear error
- [ ] Docker run failure fails task with clear error
- [ ] Nonexistent environment reference fails with clear error

### State Management
- [ ] State file correctly tracks Dockerfile changes
- [ ] State file correctly tracks .dockerignore changes
- [ ] State file correctly tracks context changes via timestamp
- [ ] State file correctly tracks pinned base image digests
- [ ] State pruning removes environment-related keys when task deleted
- [ ] Multiple tasks using same environment don't cause duplicate work

## Implementation Considerations

### 1. .dockerignore Parser

**Recommendation:** Use `pathspec` library (already widely used, well-maintained).

```bash
pip install pathspec
```

This handles all edge cases correctly (negation, wildcards, etc.) without reinventing the wheel.

**Alternative:** Implement basic subset yourself if avoiding dependencies, but this is error-prone.

### 2. Context Walk Performance

For large contexts (>10k files), walking the entire tree can be slow. Optimizations:

1. **Early exit:** Stop on first changed file (already in design)
2. **Per-environment caching:** If multiple tasks use same environment, cache context check result for that `tt` invocation
3. **Parallel checking:** Could parallelize context walk, but probably overkill

**Typical performance:**
- 1000 files: ~10ms
- 10000 files: ~100ms  
- 100000 files: ~1s

Early exit means best case (first file changed) is O(1), worst case (no changes) is O(n).

### 3. FROM Line Parsing

Dockerfile syntax is complex. Don't try to implement full parser. Instead:

**Simple regex approach:**
```python
import re

def extract_from_images(dockerfile_content):
    """
    Extract image references from FROM lines.
    Returns list of (image, digest) tuples where digest may be None.
    """
    from_pattern = re.compile(
        r'^FROM\s+(?:--platform=[^\s]+\s+)?([^\s]+?)(?:@(sha256:[a-f0-9]+))?(?:\s+AS\s+\w+)?\s*$',
        re.MULTILINE | re.IGNORECASE
    )
    
    matches = from_pattern.findall(dockerfile_content)
    return [(image, digest if digest else None) for image, digest in matches]
```

**Handles:**
- `FROM rust:1.75` → `('rust:1.75', None)`
- `FROM rust@sha256:abc...` → `('rust', 'sha256:abc...')`
- `FROM --platform=linux/amd64 rust:1.75` → `('rust:1.75', None)`
- `FROM rust:1.75 AS builder` → `('rust:1.75', None)`

**Doesn't handle:**
- ARG substitution: `FROM ${BASE_IMAGE}` → parsed but not trackable
- Complex expressions: rare in practice

**For ARG-based FROM:** Detect pattern, issue warning that tracking isn't possible.

### 4. Multi-Stage Build Consideration

```dockerfile
FROM rust:1.75@sha256:abc... AS builder
WORKDIR /build
COPY . .
RUN cargo build --release

FROM debian:slim
COPY --from=builder /build/target/release/app /usr/local/bin/
```

**Implications:**
- Must parse BOTH FROM lines
- Must track BOTH digests (if pinned)
- If either unpinned, issue warning for that specific image
- Context files affect first stage (COPY . .), not second stage

**Context tracking is still correct:** Changes to context files trigger rebuild, Docker's layer cache handles propagation through stages.

### 5. Volume Mount Edge Cases

**Relative paths in volume specs:**
```yaml
volumes:
  - ./src:/workspace/src
  - ~/.cargo:/root/.cargo
```

Must resolve:
- `./src` relative to `tasktree.yaml` location
- `~` to user's home directory

**Absolute paths:** Use as-is.

**Missing source directories:** Docker will create them (may not be desired). Consider warning or error.

### 6. Environment Definition Validation

Validate environment specs at parse time:

```python
def validate_environment(env_name, env_spec):
    """Validate environment definition."""
    if 'dockerfile' not in env_spec:
        raise ValueError(f"Environment '{env_name}' missing required field: dockerfile")
    
    if 'context' not in env_spec:
        raise ValueError(f"Environment '{env_name}' missing required field: context")
    
    dockerfile_path = resolve_path(env_spec['dockerfile'])
    if not dockerfile_path.exists():
        raise ValueError(f"Environment '{env_name}': Dockerfile not found: {dockerfile_path}")
    
    context_path = resolve_path(env_spec['context'])
    if not context_path.exists():
        raise ValueError(f"Environment '{env_name}': context directory not found: {context_path}")
    
    # Volumes and working_dir are optional, no validation needed
```

Fail fast with clear errors rather than discovering problems during execution.

### 7. Image Build Caching Across Tasks

If `build` and `test` both use `env: builder`, should we build once or twice?

**Answer:** Build once per environment per `tt` invocation.

**Implementation:**
```python
# Global cache for tt invocation
_built_images = {}

def ensure_image_built(env_name, env_spec):
    """Build Docker image if not already built this invocation."""
    if env_name in _built_images:
        return _built_images[env_name]
    
    image_tag = f"tt-env-{env_name}"
    
    subprocess.run([
        "docker", "build",
        "-t", image_tag,
        "-f", env_spec['dockerfile'],
        env_spec['context']
    ], check=True)
    
    _built_images[env_name] = image_tag
    return image_tag
```

This ensures `docker build` runs at most once per environment, even if multiple tasks use it.

### 8. Testing Strategy

**Unit tests:**
- FROM line parsing with various formats
- .dockerignore parsing and matching
- Context change detection logic
- Working directory resolution
- Task hash computation with environment

**Integration tests:**
- Create temporary Dockerfile and context
- Define task using environment
- Run task, verify execution in container
- Modify Dockerfile, verify task reruns
- Modify context file, verify task reruns
- Verify .dockerignore is respected

**Test Dockerfiles:** Use minimal base images (alpine) to keep tests fast.

## Examples

### Example 1: Basic Rust Build Environment

**Project structure:**
```
project/
  tasktree.yaml
  Dockerfile.rust
  Cargo.toml
  src/
    main.rs
```

**tasktree.yaml:**
```yaml
environments:
  rust-builder:
    dockerfile: ./Dockerfile.rust
    context: .
    volumes:
      - ./:/workspace
    working_dir: /workspace

tasks:
  build:
    env: rust-builder
    outputs: [target/release/myapp]
    cmd: cargo build --release
  
  test:
    env: rust-builder
    deps: [build]
    cmd: cargo test
```

**Dockerfile.rust:**
```dockerfile
FROM rust:1.75@sha256:abc123def456...
RUN apt-get update && apt-get install -y libssl-dev
WORKDIR /workspace
```

**Behavior:**

First run:
```
$ tt build
Building Docker image: tt-env-rust-builder
[Docker build output...]
Running: build
  cargo build --release
[Cargo output...]
```

Second run (no changes):
```
$ tt build
Skipping: build (up to date)
```

Change `src/main.rs`:
```
$ tt build
Building Docker image: tt-env-rust-builder (using cache)
Running: build
  cargo build --release
[Cargo output...]
```

Change Dockerfile comment:
```
$ tt build  
Building Docker image: tt-env-rust-builder (using cache)
Running: build
  cargo build --release
[Cargo output, but cargo uses cache]
```

Change base image digest:
```
$ tt build
Building Docker image: tt-env-rust-builder
[Docker pulls new base image...]
Running: build
  cargo build --release
[Cargo output...]
```

### Example 2: Multi-Environment Pipeline

**tasktree.yaml:**
```yaml
environments:
  builder:
    dockerfile: ./docker/Dockerfile.build
    context: ./docker/build-context/
    volumes:
      - ./:/workspace
    working_dir: /workspace

  tester:
    dockerfile: ./docker/Dockerfile.test  
    context: ./docker/test-context/
    volumes:
      - ./:/workspace
    working_dir: /workspace

tasks:
  build:
    env: builder
    outputs: [dist/app.tar.gz]
    cmd: |
      cargo build --release
      tar czf dist/app.tar.gz target/release/myapp

  unit-test:
    env: builder
    deps: [build]
    cmd: cargo test

  integration-test:
    env: tester
    deps: [build]
    cmd: |
      tar xzf dist/app.tar.gz
      pytest tests/integration/
```

**Behavior:**
- `build` uses `builder` environment, depends on files in `docker/build-context/`
- `unit-test` uses same `builder` environment (image built once)
- `integration-test` uses separate `tester` environment
- Changing test-related files only rebuilds `tester`, not `builder`

### Example 3: Unpinned Base Image Warning

**Dockerfile.python:**
```dockerfile
FROM python:3.11
RUN pip install pytest flake8
WORKDIR /app
```

**tasktree.yaml:**
```yaml
environments:
  python-env:
    dockerfile: ./Dockerfile.python
    context: .
    volumes:
      - ./:/app

tasks:
  lint:
    env: python-env
    cmd: flake8 src/
```

**Output:**
```
$ tt lint

Warning: Dockerfile.python uses unpinned base image(s):
  - python:3.11

Task Tree cannot detect if these base images have been updated on the registry.
For reproducible builds, pin to digests:
  FROM python:3.11@sha256:7a89b9526b19...

Alternatively, run 'tt --force lint' to force rebuild with latest images.

Building Docker image: tt-env-python-env
[Docker build output...]
Running: lint
  flake8 src/
[Flake8 output...]
```

### Example 4: Complex Multi-Stage Build

**Dockerfile.multi:**
```dockerfile
# Build stage
FROM rust:1.75@sha256:abc123... AS builder
WORKDIR /build
COPY Cargo.* ./
RUN cargo fetch
COPY src/ src/
RUN cargo build --release

# Runtime stage  
FROM debian:bookworm-slim@sha256:def456...
RUN apt-get update && apt-get install -y libssl3
COPY --from=builder /build/target/release/myapp /usr/local/bin/
CMD ["/usr/local/bin/myapp"]
```

**tasktree.yaml:**
```yaml
environments:
  app-builder:
    dockerfile: ./Dockerfile.multi
    context: .
    volumes:
      - ./:/build
    working_dir: /build

tasks:
  build:
    env: app-builder
    outputs: [target/release/myapp]
    cmd: echo "Build happens in Dockerfile"
```

**Behavior:**
- Both FROM lines are parsed
- Both digests are tracked  
- Changing either digest triggers rebuild
- Context changes (Cargo files, src/) trigger rebuild
- Docker's layer cache optimizes when only source changes (cargo fetch cached)

### Example 5: Dry-Run Output

```
$ tt --dry-run build test

Checking tasks...

Environment: rust-builder
  Dockerfile: ./Dockerfile.rust (unchanged)
  Context: . (src/main.rs changed: 1734567890 > 1734567000)
  Would rebuild Docker image

Would run: build
  Reason: src/main.rs changed
  Environment: rust-builder (would rebuild)

Would run: test
  Reason: dependency 'build' needs to run
  Environment: rust-builder (would use cached image)

2 tasks would run
```

## Non-Requirements (Out of Scope)

The following are explicitly out of scope for initial implementation:

1. **Docker Compose support:** Only single-container environments, no service orchestration
2. **Build arguments:** No support for `--build-arg` (future enhancement)
3. **Multi-platform builds:** No `--platform` support (future enhancement)
4. **Remote registries:** No automatic pushing to registries
5. **Image cleanup:** No automatic `docker image prune` or cleanup
6. **Podman support:** Docker-specific initially (though should be adaptable)
7. **Build secrets:** No `--secret` support (future enhancement)
8. **SSH forwarding:** No `--ssh` support (future enhancement)
9. **Custom network:** Always uses default bridge network
10. **Container orchestration:** Each task runs in ephemeral container (`--rm`)

These may be added in future iterations based on user needs.

## Migration Path

Users currently running `run-in-docker.sh tt build` can migrate as follows:

**Before (external wrapper):**
```bash
# run-in-docker.sh
#!/bin/bash
docker build -t myproject-builder -f Dockerfile.build .
docker run --rm -v $(pwd):/workspace -w /workspace myproject-builder "$@"
```

```yaml
# tasktree.yaml
tasks:
  build:
    cmd: cargo build --release
```

```bash
$ ./run-in-docker.sh tt build
```

**After (native support):**
```yaml
# tasktree.yaml
environments:
  builder:
    dockerfile: ./Dockerfile.build
    context: .
    volumes:
      - ./:/workspace
    working_dir: /workspace

tasks:
  build:
    env: builder
    cmd: cargo build --release
```

```bash
$ tt build
```

**Benefits of migration:**
- No external scripts to maintain
- Build environment is declarative and versioned
- Automatic dependency tracking for Dockerfile changes
- Dry-run support shows when rebuilds would occur
- Consistent with rest of `tt` workflow

## Open Questions for Implementation

1. **Should we support inline Dockerfile content?**
   ```yaml
   environments:
     builder:
       dockerfile_content: |
         FROM rust:1.75
         RUN apt-get update
       context: .
   ```
   **Recommendation:** No, keep it simple. Use external files.

2. **Should environment names be validated (alphanumeric only)?**
   **Recommendation:** Yes, to ensure valid Docker image tags.

3. **Should we support environment inheritance/composition?**
   ```yaml
   environments:
     base:
       dockerfile: ./Dockerfile.base
     extended:
       extends: base
       volumes: [./extra:/extra]
   ```
   **Recommendation:** No, not initially. Keep it simple.

4. **Should we cache context walk results across invocations?**
   **Recommendation:** No, state file already provides caching. Extra complexity not worth it.

5. **Should we support `--force-rebuild` to force Docker build even if cached?**
   **Recommendation:** Yes, add `--force-rebuild` flag to force `docker build --no-cache`.

## Success Metrics

Implementation is successful when:

1. Users can replace wrapper scripts with native `tt` environment definitions
2. Docker builds only occur when necessary (Dockerfile/context changes)
3. Dry-run accurately predicts when Docker rebuilds would occur
4. Performance is acceptable (< 2 second overhead for context checking on typical projects)
5. Error messages are clear when Docker operations fail
6. State management correctly tracks environment changes
7. Multiple tasks can efficiently share the same environment

## References

- Docker build documentation: https://docs.docker.com/engine/reference/commandline/build/
- Docker run documentation: https://docs.docker.com/engine/reference/commandline/run/
- .dockerignore documentation: https://docs.docker.com/engine/reference/builder/#dockerignore-file
- pathspec library: https://github.com/cpburnz/python-pathspec
- Dockerfile reference: https://docs.docker.com/engine/reference/builder/