# Implementation plan: Normalise runner definitions (`type` / `engine`)

> **Status:** not started. **Tracking issue:** [#208](https://github.com/kevinchannon/tasktree/issues/208).
> This document is self-contained: it is written so a fresh contributor (human or
> Claude) can implement the feature without the conversation that produced it.
> Read `CLAUDE.md` first — its development philosophy (small incremental commits,
> test-as-you-go, no unconditional test skips) governs *how* these slices land.

## 1. What we're building and why

Today the only runner "type" is Docker, and the parser/executor infer "this is a
Docker runner" purely from the **presence of a `dockerfile` field**
(`Runner.dockerfile` truthy). That implicit, field-presence-based discriminator
doesn't generalise: there is nowhere to hang a second containerised engine
(Podman) or a structurally different runner kind (Nix — see
[`nix-flakes-runner.md`](nix-flakes-runner.md)) without overloading more marker
fields and stacking ad-hoc `if dockerfile:` / `if flake:` branches.

The issue asks for an explicit discriminator instead:

```yaml
runners:
  my-runner:
    type: containerised   # enum, currently only "containerised"
    engine: docker         # enum, currently only "docker"
    dockerfile: ./Dockerfile
    # ...existing docker-only fields (context, volumes, ports, env_vars, run_as_root, args)
```

`type` answers "how is this runner structurally shaped" (containerised vs. some
future fundamentally different shape like `nix`). `engine` answers "which concrete
implementation of that shape" (docker vs. a future podman). Adding Podman later is
"add `podman` to the `engine` enum, reuse the containerised fields." Adding Nix
later is "add `nix` to the `type` enum, with its own field set" (already anticipated,
out of scope here, and likely to need its own schema branch per the issue text).

Per the issue, **no backward compatibility is required**: existing recipes that set
`dockerfile` without `type`/`engine` must be updated to add both, and the parser
should make this a hard validation error rather than inferring the discriminator.

## 2. Locked design decisions

1. **`type` and `engine` are required together whenever any Docker-only field is
   used.** "Docker-only fields" = `dockerfile`, `context`, `volumes`, `ports`,
   `env_vars`, `run_as_root`, `args` (build/run). If a runner sets any of these
   without `type: containerised` + `engine: docker`, parsing fails with a clear
   error naming the runner. This mirrors the existing (inverse) check in
   `Executor._validate_runner_for_task`, which already rejects Docker-only fields
   on a non-Docker runner.
2. **`type`/`engine` become the canonical discriminator everywhere**, replacing
   `bool(runner.dockerfile)` as the "is this containerised?" check. `dockerfile`
   remains the docker-*engine*-specific build source field, but it's no longer the
   thing other code branches on.
3. **Enums are deliberately narrow today**: `type` only accepts `"containerised"`,
   `engine` only accepts `"docker"`. Anything else is a validation error. This keeps
   the schema honest about what's actually implemented (per the issue: "we'll cross
   that bridge when we come to it" for Nix).
4. **No new runtime behaviour.** This is a pure schema/validation normalisation —
   Docker execution itself (`docker.py`) does not change.

## 3. How this maps onto the existing code

File:line anchors below were accurate at the time of writing — **verify before
editing**, the files churn.

- **Runner dataclass.** `src/tasktree/parser.py` `Runner` (~line 88-110). Add
  `type: str = ""` and `engine: str = ""`.
- **Parsing/validation.** `_parse_runners_from_data` (`parser.py` ~line 1860-1966)
  currently reads `dockerfile`/`context`/`volumes`/`ports`/`env_vars`/`run_as_root`
  with no `type`/`engine` concept. Add parsing of `type`/`engine`, enum validation,
  and the "Docker-only fields require type+engine" check described above.
- **Containerised-runner discriminator.** `docker.py:445`
  `is_docker_runner(env) -> bool: return bool(env.dockerfile)` is the existing
  single chokepoint for "is this a Docker runner" — change it to check
  `env.type == "containerised" and env.engine == "docker"`. This function is
  already the right shape for this change; nothing downstream of it needs touching
  beyond this line.
- **Runner-for-task validation.** `Executor._validate_runner_for_task`
  (`executor.py` ~line 469-497) currently branches on `runner.dockerfile` and its
  error messages say "(runners with a 'dockerfile' field)". Switch the branch to
  the `type`/`engine` check and update the three error message strings to
  "containerised runners (type: containerised, engine: docker)".
- **Interpreter default selection.** `Executor._resolve_interpreter`
  (`executor.py` ~line 507-541), the `if runner is not None and runner.dockerfile:`
  branch (~line 538) selecting `container_default_interpreter()`. Switch to the
  `type`/`engine` check for consistency, even though `dockerfile` truthy and
  `type==containerised` are equivalent after this change (belt-and-braces: keeps
  exactly one place that means "containerised").
- **Other `runner.dockerfile` truthiness checks** to review for the same swap (not
  necessarily all need to change — some genuinely mean "is a Dockerfile build
  needed", which is still `dockerfile`-specific, not `type`/`engine`-specific):
  `executor.py:927`, `executor.py:1080`, `executor.py:1847` (likely stay
  `dockerfile`-keyed — these are about *building/running a container*, which still
  needs the actual Dockerfile path) vs. `executor.py:475,538` and `docker.py:445`
  (these mean "is this conceptually a containerised runner" — switch to
  `type`/`engine`). Judgement call per call site; default to leaving
  build/run-path code on `dockerfile` (it needs the path anyway) and switching only
  pure classification checks.
- **Runner identity hashing.** `hash_runner_definition` (`hasher.py` ~line
  165-194) serialises the fields that affect execution/cache invalidation. Add
  `"type": env.type, "engine": env.engine` to the hashed dict so a recipe edit that
  only changes `type`/`engine` (e.g. a future docker→podman engine swap) still
  invalidates cached task state.
- **Variable-reference rewriting for imports.** `_rewrite_runner_variable_references`
  (`parser.py` ~line 944-964) rewrites `{{ var.X }}` references inside runner
  fields. `type`/`engine` are plain enum values, never templated — no change needed
  there.
- **Schema.** `schema/tasktree-schema.json` defines the runner object
  (~line 56-146). This file is an editor-assist artifact (VS Code YAML schema
  validation) — nothing in the Python parser currently validates recipes against it
  at runtime, so updating it is independent of the parser change but should still
  happen for consistency and editor UX. Add `type` (enum `["containerised"]`) and
  `engine` (enum `["docker"]`) properties, and extend the existing `if`/`then`
  block (~line 132-144, currently "if no `dockerfile`, then reject the other
  Docker-only fields") to also require `type` + `engine` whenever `dockerfile` (or
  any Docker-only field) is present.

## 4. Proposed shapes

```python
# parser.py — Runner dataclass gains:
type: str = ""    # "" (host runner) or "containerised"
engine: str = ""  # "" or "docker" (only meaningful when type == "containerised")
```

```python
# parser.py — _parse_runners_from_data, new validation alongside the existing
# dockerfile/context/volumes/ports/env_vars/run_as_root parsing:
runner_type = env_config.get("type", "")
engine = env_config.get("engine", "")

if runner_type and runner_type != "containerised":
    raise ValueError(f"Runner '{env_name}': 'type' must be 'containerised', got '{runner_type}'")
if engine and engine != "docker":
    raise ValueError(f"Runner '{env_name}': 'engine' must be 'docker', got '{engine}'")

docker_only_fields_present = bool(
    dockerfile or context or volumes or ports or env_vars or run_as_root
    or args_config.build or args_config.run
)
if docker_only_fields_present and not (runner_type == "containerised" and engine == "docker"):
    raise ValueError(
        f"Runner '{env_name}': Docker-related fields require "
        f"'type: containerised' and 'engine: docker' to be set"
    )
```

```python
# docker.py — is_docker_runner, new discriminator:
def is_docker_runner(env: Runner) -> bool:
    return env.type == "containerised" and env.engine == "docker"
```

## 5. Staged slices

Each slice is one or a few small commits **with tests**, in the project's
incremental style.

1. **Schema only.** Add `type`/`engine` properties + enum constraints to
   `schema/tasktree-schema.json`, and extend the `if`/`then` block to require them
   alongside `dockerfile`. No Python changes. *No new automated test exists for
   schema validity today — optionally add one alongside this slice: a unit test
   that loads the schema and runs `jsonschema.Draft7Validator.check_schema()` on
   it, so this file can't silently rot in future changes.*

2. **Parser: parse + validate `type`/`engine`.** Add the two fields to `Runner`,
   parse them in `_parse_runners_from_data`, enum-validate, and enforce "Docker
   fields require type+engine". *Unit tests in `test_parser.py`: parses a valid
   `type: containerised`/`engine: docker` runner; rejects a runner with
   `dockerfile` but no `type`/`engine`; rejects an unknown `type`/`engine` value.*

3. **Switch the discriminator.** Update `docker.py:is_docker_runner`,
   `executor.py:_validate_runner_for_task`, and
   `executor.py:_resolve_interpreter`'s containerised branch to key off
   `type`/`engine` instead of `bool(dockerfile)`; update the three
   `_validate_runner_for_task` error message strings. Add `type`/`engine` to
   `hash_runner_definition`. *Unit tests: `test_docker.py` (or wherever
   `is_docker_runner` is covered) updated for the new field; `test_executor.py`
   covering `_validate_runner_for_task`'s error messages; a hasher test asserting
   the hash changes when `type`/`engine` change.*

4. **Update all existing test recipes (the bulk of this issue).** Every Docker
   runner definition across the test suite needs `type: containerised` and
   `engine: docker` added next to its `dockerfile:` field. Found via
   `grep -rl "dockerfile:" tests/` — currently 20 files / ~63 occurrences:
   - Fixtures (4 files): `tests/fixtures/builtin_vars_env_in_runner/tasktree.yaml`,
     `tests/fixtures/builtin_vars_runner_volumes/tasktree.yaml`,
     `tests/fixtures/builtin_vars_var_in_runner/tasktree.yaml`,
     `tests/fixtures/imported_vars_dockerfile_path/subdir/docker.yaml`
   - Unit tests (3 files): `tests/unit/test_config.py`, `tests/unit/test_executor.py`,
     `tests/unit/test_parser.py`
   - Integration tests (3 files): `tests/integration/test_docker_build_args.py`,
     `tests/integration/test_docker_script_execution.py`,
     `tests/integration/test_integration_nested_invocations.py`
   - E2E tests (10 files): `tests/e2e/test_docker_basic.py`,
     `test_docker_complex_commands.py`, `test_docker_dependency_tracking.py`,
     `test_docker_env_change.py`, `test_docker_ownership.py`,
     `test_docker_runner.py`, `test_docker_variable_substitution.py`,
     `test_docker_volumes.py`, `test_e2e_nested_invocations.py`,
     `test_e2e_recursion_detection.py`

   This is mechanical and carries no production-code risk — split into 2-3 commits
   for reviewability (e.g. fixtures+unit, then integration+e2e) rather than one
   giant diff. *Run the full suite after each commit — this slice is "did I miss
   one" risk, not logic risk.*

5. **Docs.** Update `CLAUDE.md`'s "Task Definition Format" runner YAML block and
   "Docker Integration" section to show `type`/`engine` as required fields on
   Docker runners. Add a short forward-reference note to
   [`nix-flakes-runner.md`](nix-flakes-runner.md) §3 flagging that once this lands,
   a Nix runner's discriminator should be `type: nix` (consistent with the new
   pattern) rather than relying solely on `Runner.flake` presence — that doc was
   written before this normalisation and should be reconciled when Nix work
   starts, not silently left to contradict it.

## 6. Acceptance criteria (from issue #208)

- [ ] Runner schema requires explicit `type: containerised` + `engine: docker` for
      any runner using Docker-specific fields (`dockerfile`, `context`, `volumes`,
      `ports`, `env_vars`, `run_as_root`, `args`).
- [ ] `type`/`engine` enums are validated (currently `["containerised"]` /
      `["docker"]`); invalid or missing-when-required values are a clear parse-time
      error.
- [ ] `is_docker_runner` (and the other pure-classification call sites) key off
      `type`/`engine`, not `bool(dockerfile)`.
- [ ] `schema/tasktree-schema.json` reflects the shape proposed in the issue.
- [ ] All existing tests updated and passing with the new required fields; no
      runtime/execution behaviour changes for users beyond the new required YAML
      fields.
- [ ] `CLAUDE.md` documents the new required fields.

## 7. Notes / non-goals

- **No Podman or Nix implementation here** — this slice only normalises the schema
  so those can be added later without another breaking restructure. Podman would
  be "add `podman` to the `engine` enum + a podman code path in `docker.py` (or a
  sibling module)"; Nix is already separately planned in
  [`nix-flakes-runner.md`](nix-flakes-runner.md) and should adopt `type: nix` once
  it starts, for consistency with this discriminator.
- **No backward-compatibility shim.** Per the issue, recipes using `dockerfile`
  without `type`/`engine` should simply fail to parse with a clear message — no
  deprecation period, no auto-inference fallback.
