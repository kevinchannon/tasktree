# Implementation plan: Nix flakes runner (`runner: nix`)

> **Status:** not started. **Tracking issue:** [#197](https://github.com/kevinchannon/tasktree/issues/197).
> This document is self-contained: it is written so a fresh contributor (human or
> Claude) can implement the feature without the conversation that produced it.
> Read `CLAUDE.md` first — its development philosophy (small incremental commits,
> test-as-you-go, no unconditional test skips) governs *how* these slices land.

## 1. What we're building and why

Add `nix` as a new runner type, selectable exactly like the Docker runner:

```yaml
runners:
  nix:
    flake: .            # flakeref (local path); the marker that makes this a nix runner
    devshell: default   # devShell attr -> devShells.<system>.<devshell>; default "default"

tasks:
  build:
    run_in: nix
    cmd: cargo build    # cargo comes from the flake's devShell, not the host
```

**Nix is an environment provider, not a sandbox.** It gives a pinned, reproducible
toolchain. It gives **no** process/network/filesystem isolation, and that is by
design. The task runs in the **host process tree** with the devShell's environment
merged in.

### Nix concepts you need

- **flake**: a directory with `flake.nix` (declares pinned inputs + outputs) and
  `flake.lock` (records exact input revisions/hashes — the reproducibility anchor).
- **devShell**: a flake output describing a dev environment (toolchain + env vars).
  Default lives at `devShells.<system>.default`; a flake may define others (`.#ci`).
- **`nix print-dev-env --json <flakeref>`**: evaluates a devShell and emits it as
  structured JSON instead of dropping you into an interactive shell. Shape:
  ```json
  {
    "variables": {
      "PATH":      { "type": "exported", "value": "/nix/store/.../bin:..." },
      "shellHook": { "type": "var",      "value": "echo hi; export FOO=bar" }
    },
    "bashFunctions": { ... }
  }
  ```
  The exported `variables` are the toolchain as plain data we can merge into a child
  process's environment — no container needed.
- **shellHook**: arbitrary bash a devShell runs *on entry* (activate a venv, set
  `PKG_CONFIG_PATH`, etc.). With `--json` you get the hook **text**, not its effects;
  the static `variables` do not reflect what the hook would set at runtime — so to be
  faithful you must run the hook yourself.

## 2. Locked design decisions

These were decided deliberately. Do not silently revisit them; if you think one is
wrong, raise it on the issue first.

1. **shellHook → honour, realise once.** Realise the devShell by *entering* it once:
   run bash that applies the env, `eval "$shellHook"`, then dumps the resulting
   environment (`export -p`). Capture and cache that post-hook environment. This
   satisfies the issue's "realise + cache" requirement and runs the hook once per
   realisation (not per task), so side-effects/banners happen once.
2. **Flakerefs v1 → local path only** (`.`, `path:./sub`). A local flake has a
   readable `flake.lock`, which is what "honour the lock" and "hash on locked input
   narHashes" actually require. **Reject** `github:`/`git+`/registry refs in v1 with a
   clear "remote flakerefs are not yet supported (planned)" error. Remote refs are a
   clean follow-up ticket.
3. **`--no-write-lock-file`** is always passed (older Nix: `--no-update-lock-file`) so
   a task run never rewrites `flake.lock`.
4. **Interpreter default = bash.** devShells conventionally assume a bash-like
   environment. This uses the existing per-runner interpreter-default mechanism.
5. **Host environment is inherited by default** (non-isolation). Nested `tt` calls
   must keep working because `tt` stays on `PATH` in the child. This caveat **must**
   be documented because Docker-runner users will expect isolation they won't get.

## 3. How this maps onto the existing code

The runner system already keys off a single marker field, so this is a clean add.
File:line anchors below were accurate at the time of writing — **verify before
editing**, the files churn.

- **Runner type detection.** Runners now carry an explicit `type`/`engine`
  classification (`Runner.type`, `Runner.engine` — `src/tasktree/parser.py`,
  `Runner` dataclass ~line 88-125; `docker_module.is_docker_runner` checks
  `type == "containerised" and engine == "docker"`, used in dispatch in
  `src/tasktree/executor.py` ~line 1080) instead of inferring "container runner"
  from `dockerfile` presence. A Nix runner should set `type: nix` (a new entry in
  `VALID_RUNNER_TYPES`) with no `engine` — Nix isn't a containerised runner, so the
  `engine` field doesn't apply. `Runner.flake` is the field that carries the actual
  flakeref.
- **Execution path.** A nix task stays on the **host** path
  (`Executor._run_command_as_script`, `executor.py` ~line 1149). It only needs the
  realised devShell env merged into the `env` dict that
  `_prepare_env_with_exports` (`executor.py` ~line 1183/276) already builds. **None**
  of the Docker machinery (volumes, ports, UID/GID mapping, `run_in_container`) is
  touched.
- **Interpreter default.** `container_default_interpreter()` returns `sh` and is
  selected in `Executor._resolve_interpreter` (`executor.py` ~line 507-541, the
  `is_docker_runner(runner)` branch ~line 538). Add a parallel `nix` default
  returning `Interpreter(cmd="bash")` and a branch `if runner.type == "nix":`
  before the Docker one.
- **Runner identity for stale-detection.** `hash_runner_definition` in
  `src/tasktree/hasher.py` (~line 165-195) serialises the fields that affect
  execution. Extend it with the nix runner identity = `(flakeref, devShell attr,
  locked input narHashes)`.
- **New module `src/tasktree/nix.py`**, mirroring `src/tasktree/docker.py`'s
  `DockerManager` (`docker.py` ~line 32): availability check, realise-and-cache,
  in-process cache dict. The Docker availability check
  (`DockerManager._check_docker_available`, `docker.py` ~line 361) is the template
  for `_check_nix_available`.
- **Schema.** `schema/tasktree-schema.json` defines the runner object; add `"nix"`
  to the `type` enum and add `flake`/`devshell` properties (conditionally required
  when `type: nix`, mirroring how `type`/`engine: docker` gate the Docker-only
  fields). Runner-parsing lives in `parser.py` ~line 1880-1966.

## 4. Proposed shapes

```python
# parser.py — Runner dataclass gains:
flake: str = ""        # flakeref; required (and only valid) when type == "nix"
devshell: str = "default"

# executor.py — new default, parallel to container_default_interpreter():
def nix_default_interpreter() -> Interpreter:
    return Interpreter(cmd="bash")

# nix.py
class NixError(Exception): ...

class NixManager:
    def __init__(self, project_root: Path, logger: Logger): ...
    def _check_nix_available(self) -> None: ...      # nix present AND flakes enabled
    def realise_env(self, runner: Runner, process_runner: ProcessRunner) -> dict[str, str]: ...
    #   runs print-dev-env, applies+evals shellHook, captures post-hook env, caches
    #   keyed on (flakeref, devshell attr, locked narHashes)
```

`_check_nix_available` must fail fast and clearly when **either** `nix` is absent
**or** `nix-command`/`flakes` is missing from `experimental-features` (check via
`nix --version` for presence and `nix config show experimental-features` for the
features), pointing the user at the exact config they need.

## 5. Staged slices

Each slice is one or a few small commits **with tests**, in the project's incremental
style. Land them in order; slices 1–4 produce a usable runner, 5–6 complete the
acceptance criteria, 7 is documentation.

1. **Parse `flake`/`devshell` into `Runner` + JSON schema.** Add `"nix"` to the
   `type` enum, add the `flake`/`devshell` fields, schema entries, and parser
   validation (`type: nix` requires `flake`, mirroring the `type: containerised`/
   `engine: docker` pairing added for Docker runners; flake must be a local path
   that exists; reject remote-looking refs like `github:`/`git+`/`<name>` registry
   shorthand with the "planned" message). No execution yet. *Unit tests on the
   parser + a schema validation test.*
2. **`nix.py`: `NixError` + `_check_nix_available()`.** Fast, clear failure if `nix`
   is absent or `nix-command`/`flakes` not enabled. *Unit tests mocking subprocess
   (`nix --version`, `nix config show`).*
3. **`NixManager.realise_env()` — no cache, no shellHook yet.** Run
   `nix print-dev-env --json --no-write-lock-file <flakeref>` (selecting the devShell
   attr), parse the JSON, return the exported `variables` as `dict[str, str]`. *Unit
   test with a mocked JSON payload.*
4. **Wire into the executor (the end-to-end slice).** Dispatch: `if env.flake:`
   realise the env and merge it into the env passed to `_run_command_as_script`; add
   the `nix → bash` interpreter default in `_resolve_interpreter`. *Add an e2e test
   gated with `@unittest.skipUnless(nix_available(), ...)` that runs a task inside a
   tiny fixture flake's devShell and asserts a devShell-provided tool/var is visible.*
   A conditional skip (CI without Nix) is explicitly allowed by `CLAUDE.md`; an
   unconditional skip is not.
5. **shellHook honouring via realise-once.** Change realisation to enter the env,
   `eval "$shellHook"`, then capture the resulting environment (`export -p`) instead
   of taking only the static exported variables. *Test that a var set by the hook
   reaches the task.*
6. **Caching + runner identity.** Read locked input narHashes from `flake.lock` (or
   `nix flake metadata --json`); add an in-process cache of the realised env keyed on
   `(flakeref, devshell attr, narHashes)`; extend `hash_runner_definition` with the
   same identity so stale-detection re-runs tasks when flake inputs change. *Tests on
   both the cache behaviour and the hash.*
7. **Docs.** Update `README.md`, the runner section of `CLAUDE.md`, and
   `schema/README.md`: the **non-isolation caveat**, host-env-inheritance default,
   "nested `tt` still works", "shellHook runs at realisation", supported flakeref
   forms (local only for now), and the `nix` + flakes-enabled prerequisite.

## 6. Acceptance criteria (from issue #197)

- [ ] `runner: nix` selectable as a peer of the container runner(s).
- [ ] Resolves a devShell from a flakeref, default `devShells.<system>.default`, with
      an optional attr override (`devshell:`).
- [ ] Environment realised via `nix print-dev-env --json` and cached, keyed on locked
      input hashes.
- [ ] `flake.lock` is honoured and never rewritten (`--no-write-lock-file`).
- [ ] Runner identity used for hashing includes flakeref, devShell attr, and locked
      input narHashes.
- [ ] Nix runner defaults its interpreter to `bash` via the per-runner default
      mechanism.
- [ ] Absent `nix` or disabled flakes `experimental-features` → fast, clear failure
      pointing at the required configuration.
- [ ] Host-environment inheritance is the default and documented, including the
      non-isolation caveat; nested `tt` calls keep working under the Nix runner.
- [ ] `shellHook` honoured (realise-once) and documented.

## 7. Notes / non-goals

- **No** Docker-style machinery: no volumes, ports, UID/GID mapping, image building.
- Remote flakerefs (`github:`, `git+…`, registry) are out of scope for v1 — reject
  with a clear "planned" message.
- An earlier idea of using Nix to do *building* with incremental recompilation was
  rejected (incompatible with tasktree's own stale-task detection). In this design
  Nix only provides the environment, so that tension does not arise.
- Reference for the JSON format:
  <https://nixos.org/manual/nix/stable/command-ref/new-cli/nix3-print-dev-env.html>
