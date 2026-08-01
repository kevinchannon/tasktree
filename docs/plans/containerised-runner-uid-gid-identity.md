# Implementation plan: containerised runner UID/GID identity (`{{ tt.uid }}` / `{{ tt.gid }}`)

> **Status:** not started. **Tracking issue:** [#215](https://github.com/kevinchannon/tasktree/issues/215).
> This document is self-contained: it is written so a fresh contributor (human or
> Claude) can implement the feature without the conversation that produced it.
> Read `CLAUDE.md` first — its development philosophy (small incremental commits,
> test-as-you-go, no unconditional test skips) governs *how* these slices land.

## 1. What we're building and why

Containerised runners pass `--user <uid>:<gid>` numerically (`docker.py:240-241`)
so files written into mounted volumes are owned by the host user. That's
sufficient for **ownership** but not **identity**: if the image has no passwd
entry for that UID, `id -un`/`whoami`/`getpwuid()` fail and `$HOME` falls back
to `/`, which isn't writable — breaking anything with a dotfile cache (`pip`,
`npm`, `cargo`, `git config --global`). The only current escape hatch,
`run_as_root: true`, throws away the ownership guarantee to fix this.

The fix does **not** belong in Tasktree rewriting user Dockerfiles (it would
have to guess `useradd` vs `adduser` per base image). It belongs in the
project's own Dockerfile, via a `getent`-guarded `RUN` step that creates a
passwd entry at the host's UID/GID — a pattern that is a no-op (and safe) when
the image already ships that UID (e.g. `ubuntu:24.04`'s `ubuntu` user). What's
missing is a way for that Dockerfile to *know* the host's UID/GID: there's no
builtin template variable for it today, only `{{ tt.user_name }}`, which is
the wrong axis (containers must match *numerically*).

Full detail and the verified before/after `id`/`$HOME` behaviour is in the
issue body — not repeated here.

## 2. Scope: what's in / what's out

**In scope** (issue's items 1 and 2):
- `{{ tt.uid }}` / `{{ tt.gid }}` builtin variables.
- Documentation: state the numeric-mapping/identity gap plainly in the
  containerised-runner docs, with the `getent`-guarded Dockerfile prelude
  (Debian/Ubuntu form from the issue, plus an Alpine variant) as the
  recommended fix.

**Explicitly deferred** (not this plan):
- Issue's item 3 (`-e HOME=<writable>` fallback when the UID can't be
  resolved). The issue author's own write-up flags this as possibly not worth
  the complexity once (1) and (2) ship — it interacts with `HOME` being in
  `PROTECTED_ENV_VARS` (`executor.py:125-134`, meaning Tasktree would become
  sole authority on `$HOME`) and can't reliably detect "UID unresolvable"
  without an extra container start via `capture_in_container`. Revisit only if
  users still hit the `$HOME=/` failure after (1)+(2) ship.
- The `tt-env-{name}` fixed image tag (`docker.py:103`) not incorporating the
  UID, so two users on one Docker daemon with different UIDs could contend for
  the same tag. Issue author flags this as "probably rare"; out of scope here,
  worth its own follow-up issue if it's ever hit in practice.

## 3. Design decisions

### 3.1 Where the variables get collected

`{{ tt.uid }}` / `{{ tt.gid }}` must land in
`Executor._collect_early_builtin_variables` (`executor.py:219-271`), alongside
`user_home`/`user_name` — **not** in `_collect_builtin_variables`
(`executor.py:273-297`, which only adds `working_dir` on top of the early set).
Confirmed by tracing both call sites in `_execute_task`
(`executor.py:1064-1090`) and in `_render_runner_environment`
(`executor.py:1300-1375`, the function that substitutes `args.build`,
`args.run`, `volumes`, `ports`, `working_dir`, `dockerfile`, `context`): the
runner-field substitution path uses the *full* builtin-vars dict, which itself
starts from the early collector's output (`executor.py:291`). Adding the keys
in one place satisfies the issue's full acceptance list (`args.build`,
`args.run`, `volumes`, `ports`, `working_dir`) without touching either
substitution call site.

### 3.2 Windows: no eager crash

The existing `user_home` pattern (`executor.py:252-259`) eagerly resolves for
*every* task on *every* platform and raises `ExecutionError` on failure. That
pattern cannot be copied verbatim for `uid`/`gid`: `os.getuid`/`os.getgid`
don't just risk raising on Windows, they don't exist as attributes at all, and
the early-vars dict is built unconditionally for every task run — copying the
eager pattern would break *all* task execution on Windows, not just tasks that
reference `tt.uid`/`tt.gid`.

Decision: only add the `uid`/`gid` keys to the dict on POSIX (mirroring
`DockerManager._should_add_user_flag()`'s `platform.system() != "Windows"`
check, or `hasattr(os, "getuid")`). Do **not** add a lazy Windows-specific
raise. The substitution engine already raises an actionable error when a
template references a `tt.*` name absent from the dict
(`substitution.py:213-221`: `"Built-in variable '{{ tt.uid }}' is not
defined. Available built-in variables: ..."`). That satisfies the issue's
"actionable error, not empty substitution" criterion with no new code path,
in keeping with `CLAUDE.md`'s minimalism guidance (no error handling for a
scenario an existing mechanism already covers correctly).

**Open question for the issue author** (see §5): the issue's write-up leaned
towards a Windows-*named* error message, matching `user_home`'s style. This
plan proposes relying on the generic "not defined" message instead, since
producing a bespoke message would mean computing `tt.uid` lazily-per-reference
(more moving parts) rather than eagerly-when-supported (what every other
builtin does). Worth explicit sign-off before implementing either way.

### 3.3 The runner-hash acceptance criterion needs re-targeting

The issue proposes testing that "changing the host UID changes the runner
hash," reasoning that `args_build` is already in `hash_fields()`
(`parser.py:153-160`). Traced `hash_runner_definition()` (`hasher.py:165`) to
its call site (`executor.py:1652-1660`): the `env` passed in is
`self.recipe.get_runner(env_name)` — the **raw, unrendered** runner
definition. Its `args.build` is still the literal string
`"UID={{ tt.uid }}"`, not the rendered numeric value, so the runner hash is
identical regardless of the host's actual UID. The issue's assumption doesn't
hold as written.

That's not actually a gap, for two reasons:
- `.tasktree-state` is git-ignored (`.gitignore:150`), so state is per-machine
  — there's no scenario where one machine's cached "runner unchanged" hash is
  read on a different machine with a different UID.
- Freshness is separately protected by the **image content fingerprint**
  (`DockerManager.image_content_fingerprint`, stored as
  `_runner_image_fp_{env_name}`, `executor.py:1940-1947`), which hashes the
  built image's `RootFS.Layers` — this *does* change when a build-arg-driven
  Dockerfile step produces different content, because Docker's own build
  cache is keyed on the `ARG` value.

Slice 3 (below) should assert against the **image fingerprint changing** /
**task re-running** when `tt.uid` differs between two runs, not against
`hash_runner_definition()` equality — asserting the latter would bake a false
expectation into the test suite.

## 4. Slices (small, sequential commits)

**Slice 1 — `{{ tt.uid }}` / `{{ tt.gid }}` builtin variables**
- `executor.py`: extend `_collect_early_builtin_variables`, POSIX-guarded, per
  §3.2.
- Unit tests (near the existing `user_home`/`user_name` tests, likely
  `tests/unit/test_executor.py`):
  - renders `os.getuid()`/`os.getgid()` as decimal strings via
    `{{ tt.uid }}`/`{{ tt.gid }}` (mock `os.getuid`/`os.getgid`).
  - referencing `{{ tt.uid }}` under a simulated Windows platform raises the
    existing "not defined" error rather than resolving to `""` or crashing.
  - a task that does **not** reference `tt.uid`/`tt.gid` still executes
    normally when simulated on Windows — regression guard for the "eager
    eval breaks everyone" failure mode this design avoids.
- Estimated size: ~15-25 lines of production code plus tests. One commit.

**Slice 2 — propagation to all runner-field substitution points**
- Integration test exercising a `DockerRunner` with `args.build` referencing
  `{{ tt.uid }}`/`{{ tt.gid }}`, asserting the rendered `docker build` command
  contains the numeric values (mock subprocess, reusing the existing
  docker-build test pattern).
- Spot-check one more field beyond `args.build` (e.g. `args.run` or
  `volumes`) — all funnel through the same `subst()` closure
  (`executor.py:1340-1341`), so exhaustive per-field coverage isn't needed.
- Estimated size: small, mostly test code. One commit.

**Slice 3 — freshness behaviour when `tt.uid` changes**
- Test that changing the mocked UID between two invocations against the same
  `DockerRunner` causes the image fingerprint to change / the task to
  re-run — per §3.3, target the image fingerprint mechanism, not
  `hash_runner_definition()` equality. Needs a look at the existing docker
  freshness-test fixtures at implementation time to find the right seam.
- Estimated size: small-medium; scope depends on fixture shape, confirm at
  implementation time.

**Slice 4 — documentation**
- Extend the Docker Integration section of `README.md` (~line 177) with:
  (a) a plain statement that containers run under the host's numeric
  UID:GID and that identity (`id`/`whoami`/`$HOME`) needs a matching passwd
  entry in the image; (b) the `getent`-guarded Dockerfile prelude from the
  issue (Debian/Ubuntu form); (c) an Alpine variant
  (`adduser -u "$UID" -D runner`); (d) a short example wiring
  `{{ tt.uid }}`/`{{ tt.gid }}` into `args.build`.
- Doc-only commit, no production code.

Not covered by this plan: issue item 3 (`-e HOME=...` fallback), and the
image-tag UID-collision question — see §2.

## 5. Open questions for @kevinchannon

1. §3.2 — is the existing generic "Built-in variable not defined" message an
   acceptable "actionable error" for referencing `tt.uid`/`tt.gid` on
   Windows, or is a bespoke Windows-named message wanted (at the cost of
   making `uid`/`gid` resolve lazily-per-reference instead of eagerly like
   every other builtin)?
2. §3.3 — confirm the corrected acceptance target for the UID-change
   freshness test (image fingerprint / task re-execution) rather than
   `hash_runner_definition()` equality, since the issue text assumed the
   latter.
3. Any interest in a follow-up issue for the `tt-env-{name}` image-tag
   collision noted in the original report, or leave it as "probably rare"
   per the issue author's own assessment?

## 6. Estimated size

Four small commits (variables + Windows guard, propagation test, freshness
test, docs), each independently reviewable per `CLAUDE.md`'s incremental-commit
philosophy. Rough total: 40-70k tokens including test-writing and doc-writing —
fits in a single follow-up session.
