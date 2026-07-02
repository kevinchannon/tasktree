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
    type: nix           # discriminator; selects the Nix runner (peer of `type: containerised`)
    flake: .            # flakeref (local path)
    devshell: default   # devShell attr -> devShells.<system>.<devshell>; default "default"

tasks:
  build:
    run_in: nix
    cmd: cargo build    # cargo comes from the flake's devShell, not the host
```

> **Runner declaration changed.** Runners are now declared with an explicit `type:`
> discriminator (`type: containerised` + `engine: docker` for Docker), rather than
> being inferred from the presence of a `dockerfile` field. The Nix runner is declared
> `type: nix`. Nix is **not** a containerised runner, so it takes no `engine`.

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

- **Runners are a polymorphic class hierarchy, not a flag-carrying struct.** In
  `src/tasktree/parser.py` (~line 88-165): `Runner` (abstract: `name`,
  `interpreter`, `working_dir`, `hash_fields()`) → `HostRunner` (host execution) and
  `ContainerisedRunner` (abstract: `args`, `volumes`, `ports`, `env_vars`,
  `run_as_root`) → `DockerRunner` (`dockerfile`, `context`). **The class encodes the
  classification — there is no stored `type`/`engine` field on the object.** `type`
  and `engine` are *recipe-YAML discriminator strings only* (`VALID_RUNNER_TYPES`,
  `VALID_RUNNER_ENGINES` ~line 88-91). Dispatch is by `isinstance`, e.g.
  `isinstance(env, ContainerisedRunner)` in `executor.py` ~line 1039.
- **Add a new `NixRunner(Runner)`** — a **peer of `HostRunner` and
  `ContainerisedRunner`** (Nix is *not* containerised, so it does **not** extend
  `ContainerisedRunner`). Fields: `flake: str` and `devshell: str = "default"`.
  Override `hash_fields()` to return `{flake, devshell, narhashes}`.
- **Factory dispatch.** Building runners goes through `runner_from_config(name,
  config, *, interpreter)` (`parser.py` ~line 2000), which branches on the YAML
  `type`: no `type` → `HostRunner`; `type: containerised` →
  `containerised_runner_from_config` (~line 2045, branches on `engine`). Add
  `NIX_RUNNER_TYPE = "nix"` to `VALID_RUNNER_TYPES` and a `type == "nix"` branch in
  `runner_from_config` that builds the `NixRunner` (mirror the containerised path
  with a small `nix_runner_from_config` helper). Both the recipe parser and the
  machine-config loader build runners through `runner_from_config`.
- **Config-key guards.** `runner_from_config` rejects container-only keys that appear
  without a `type` (via `_CONTAINER_CONFIG_KEYS`, ~line 2027). Add the analogous
  guard so `flake`/`devshell` are rejected on non-Nix runners, and container keys are
  rejected on a Nix runner.
- **Execution path.** A Nix task stays on the **host** path
  (`Executor._run_command_as_script`, `executor.py` ~line 1108). It only needs the
  realised devShell env merged into the `env` dict that
  `_prepare_env_with_exports` (`executor.py` ~line 276) already builds. Detection is
  `isinstance(env, NixRunner)`. **None** of the Docker machinery (volumes, ports,
  UID/GID mapping, `run_in_container`) is touched.
- **Interpreter default.** `container_default_interpreter()` returns `sh` and is
  selected in `Executor._resolve_interpreter` (`executor.py` ~line 469-503, the
  `isinstance(runner, ContainerisedRunner)` branch ~line 500). Add a
  `nix_default_interpreter()` returning `Interpreter(cmd="bash")` and a parallel
  `isinstance(runner, NixRunner)` branch.
- **Runner identity for stale-detection — mostly free.** `hash_runner_definition`
  in `src/tasktree/hasher.py` (~line 165-190) already keys on `type(env).__name__`
  (`"kind"`) plus `env.hash_fields()`. So a `NixRunner` is automatically distinguished
  by class, and its identity comes entirely from `NixRunner.hash_fields()` returning
  `{flake, devshell, narhashes}` — **no edit to `hasher.py` is required**.
- **New module `src/tasktree/nix.py`**, mirroring `src/tasktree/docker.py`'s
  `DockerManager` (`docker.py` ~line 32): availability check, realise-and-cache,
  in-process cache dict. The Docker availability check
  (`DockerManager._check_docker_available`, `docker.py` ~line 361) is the template
  for `_check_nix_available`.
- **Schema.** `schema/tasktree-schema.json` defines the runner object; add `"nix"`
  to the `type` enum and add `flake`/`devshell` properties (conditionally required
  when `type: nix`, mirroring how the `type`/`engine: docker` combination gates the
  Docker-only fields). Runner-parsing lives in `parser.py` ~line 2137 onward.

## 4. Proposed shapes

```python
# parser.py — new runner subclass, a peer of HostRunner / ContainerisedRunner:
NIX_RUNNER_TYPE = "nix"          # add to VALID_RUNNER_TYPES

@dataclass
class NixRunner(Runner):
    flake: str = ""              # flakeref (local path); required for a Nix runner
    devshell: str = "default"    # devShells.<system>.<devshell>
    narhashes: tuple[str, ...] = ()   # locked input narHashes (filled at realise time / slice 6)

    def hash_fields(self) -> dict:
        return {"flake": self.flake, "devshell": self.devshell,
                "narhashes": sorted(self.narhashes)}

# parser.py — factory branch inside runner_from_config, mirroring the
# containerised path (dispatch on the YAML `type` string):
def nix_runner_from_config(name, config, *, interpreter=None) -> NixRunner: ...
#   validates flake (local path, exists, not a remote ref), reads devshell

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

1. **Add `NixRunner` + `type: nix` parsing + JSON schema.** Add the `NixRunner(Runner)`
   subclass and its `hash_fields()`; add `NIX_RUNNER_TYPE` to `VALID_RUNNER_TYPES`;
   add a `type == "nix"` branch (`nix_runner_from_config`) to `runner_from_config`;
   add the config-key guards; add `"nix"` to the schema `type` enum plus
   `flake`/`devshell` properties. Parser validation: `type: nix` requires `flake`;
   flake must be a local path that exists; reject remote-looking refs
   (`github:`/`git+`/`<name>` registry shorthand) with the "planned" message. No
   execution yet. *Unit tests on the parser (incl. `runner_from_config` returns a
   `NixRunner`, and abstract-base guards still hold) + a schema validation test.*
2. **`nix.py`: `NixError` + `_check_nix_available()`.** Fast, clear failure if `nix`
   is absent or `nix-command`/`flakes` not enabled. *Unit tests mocking subprocess
   (`nix --version`, `nix config show`).*
3. **`NixManager.realise_env()` — no cache, no shellHook yet.** Run
   `nix print-dev-env --json --no-write-lock-file <flakeref>` (selecting the devShell
   attr), parse the JSON, return the exported `variables` as `dict[str, str]`. *Unit
   test with a mocked JSON payload.*
4. **Wire into the executor (the end-to-end slice).** Dispatch: `isinstance(env,
   NixRunner)` → realise the env and merge it into the env passed to
   `_run_command_as_script`; add the `nix → bash` interpreter default via a new
   `isinstance(runner, NixRunner)` branch in `_resolve_interpreter`. *Add an e2e test
   gated with `@unittest.skipUnless(nix_available(), ...)` that runs a task inside a
   tiny fixture flake's devShell and asserts a devShell-provided tool/var is visible.*
   A conditional skip (CI without Nix) is explicitly allowed by `CLAUDE.md`; an
   unconditional skip is not. **This slice requires the CI changes in §8** — without
   them the e2e test only ever runs locally on a dev machine that happens to have
   Nix, and silently skips in CI forever (technically a *conditional* skip, but a
   condition that's never true anywhere in the pipeline is a coverage gap in
   practice, not just in theory).
5. **shellHook honouring via realise-once.** Change realisation to enter the env,
   `eval "$shellHook"`, then capture the resulting environment (`export -p`) instead
   of taking only the static exported variables. *Test that a var set by the hook
   reaches the task.*
6. **Caching + runner identity.** Read locked input narHashes from `flake.lock` (or
   `nix flake metadata --json`) and populate `NixRunner.narhashes`; add an in-process
   cache of the realised env keyed on `(flakeref, devshell attr, narHashes)`. Because
   `hash_runner_definition` already folds in `type(env).__name__` and
   `env.hash_fields()`, including the narHashes in `NixRunner.hash_fields()` makes
   stale-detection re-run tasks when flake inputs change — **no `hasher.py` edit
   needed**. *Tests on the cache behaviour and on `NixRunner.hash_fields()` /
   `hash_runner_definition` reflecting a narHash change.*
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

## 8. CI workflow updates

`.github/workflows/test.yml` currently has **no awareness of Nix at all** — it
installs Docker's prerequisite (nothing; Docker ships on the `ubuntu-latest` image)
and pre-pulls an Alpine image for Docker E2E, but there is no equivalent for Nix. As
written, the slice-4 e2e test (`skipUnless(nix_available())`) would run **nowhere in
CI** — a conditional skip is fine per `CLAUDE.md`, but only if the condition is
actually satisfied somewhere in the pipeline. That means slice 4 is not truly "done"
until this section's changes land alongside it.

### What needs to change, concretely

The `test` job runs a `matrix: os: [ubuntu-latest, macos-latest, windows-latest]`.
Nix has no native Windows support (WSL only, and GitHub-hosted `windows-latest`
doesn't have WSL preconfigured for this) — mirror the existing Docker E2E pattern
(`if: runner.os == 'Linux'`, `test.yml` line 33/43) but for **Linux + macOS**, since
unlike Docker, Nix installs cleanly and without a licensing/daemon story on GitHub's
`macos-latest` runners too:

1. **Install Nix with flakes enabled**, gated `if: runner.os != 'Windows'`, before the
   test steps. Use an installer action rather than hand-rolling install +
   `experimental-features` config:
   - **`DeterminateSystems/nix-installer-action`** (recommended) — fast, and enables
     `nix-command`/`flakes` by default, so no extra config step needed. This is the
     natural fit since it minimises the CI YAML surface.
   - Alternative: `cachix/install-nix-action`, which requires an explicit
     `extra_nix_config: | experimental-features = nix-command flakes` block to match
     what slice 2's `_check_nix_available()` requires.
2. **A fixture flake for the e2e test** (referenced in slice 4) needs a *committed*
   `flake.lock` so CI resolves the same pinned inputs as local dev — consistent with
   the "honour and never rewrite the lock" design decision (§2.2/§2.3). First run in
   CI still needs network access to fetch the flake's inputs from the Nix binary
   cache (GitHub-hosted runners have outbound network by default, so this is fine,
   just not instant).
3. **New "Run E2E Nix tests" step**, gated the same way as the existing "Run E2E
   Docker tests" step (`if: runner.os == 'Linux'` → extend/parallel condition for
   Nix), running just the new Nix e2e test module so a Nix evaluation failure doesn't
   get lost in the general E2E step's output.
4. **Windows stays a no-op for Nix**, same shape as Docker already is on
   `windows-latest` — the e2e test's `skipUnless` naturally skips it there, no
   special-casing needed in the workflow beyond not installing Nix on that leg.
5. **Optional but recommended: cache the Nix store** (e.g.
   `DeterminateSystems/magic-nix-cache-action`) to avoid re-fetching `nixpkgs` on
   every run — `nix print-dev-env` evaluation cost is exactly the wall-clock problem
   the issue's caching design is trying to avoid, and an uncached CI run pays it on
   every single invocation across the 2×Python-version × 2×OS matrix legs that would
   gain Nix. Not required for correctness; worth adding in the same slice that adds
   the installer step, or immediately after, if CI minutes become a concern.

### Where this lands in the slice plan

Land the CI wiring together with **slice 4** (the executor wiring), since that's the
first slice with anything for the e2e test to exercise. `lint`, `release.yml`, and
`validate-pipx-install.yml` need no changes — none of them run the test suite against
a Nix runner.
