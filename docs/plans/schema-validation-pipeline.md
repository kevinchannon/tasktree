# Implementation plan: runtime schema validation pipeline

> **Status:** not started. **Tracking issue:** [#43](https://github.com/kevinchannon/tasktree/issues/43).
> This document is self-contained: it is written so a fresh contributor (human or
> Claude) can implement the feature without the conversation that produced it.
> Read `CLAUDE.md` first — its development philosophy (small incremental commits,
> test-as-you-go, no unconditional test skips) governs *how* these slices land.

## 1. What we're building and why

Today `schema/tasktree-schema.json` is used only by editor tooling; all runtime
validation is hand-written (~128 `raise ValueError(...)` sites in `parser.py`,
with ~232 unit-test assertions pinned to the exact message text). This work
restructures parsing into an explicit pipeline so the JSON schema becomes the
primary structural validator at runtime:

1. Read the tasktree YAML from disk (errors: not valid YAML).
2. Merge all imports into **one raw dict** — namespacing, `run_in` blanket
   overrides and pinned-runner reference rewrites applied as dict transforms
   (errors: missing import files, circular imports).
3. Compute the tasks reachable from the invoked task and prune the rest
   (errors: reachable task has a non-existent dependency).
4. Prune runners/interpreters not referenced by any reachable task
   (errors: reachable task references a non-existent runner/interpreter).
5. **Schema-validate the pruned merged tree** (JSON schema used here).
6. Evaluate the variables required by the surviving tasks (errors: variable
   evaluation failures).
7. Render runners and interpreters (Jinja) — these render **once**, before tasks.
8. Render and execute tasks one-by-one in dependency order (outputs of one task
   flow into later ones, so simultaneous rendering is impossible).

Checks that are inherently graph- or lifecycle-based stay as Python forever:
circular imports, dependency-name existence (falls out of step 3), variable
cycles, and lazy pinned-runner resolution.

## 2. Locked design decisions

These were settled in the issue #43 discussion. Do not re-litigate them
mid-implementation; if one proves untenable, stop and raise it.

1. **Typed-but-templatable fields** (`min`/`max`, `ports`, docker build `args`,
   …): schema accepts `oneOf` — the native type, OR a string that must match
   `\{\{.+\}\}` (so a plain typo like `min: "fivee"` still fails). The
   author-time file schema gets the same loosening, since users legitimately
   write templates in these fields in their editors today.
2. **Prune before validating — tolerance is a feature.** Errors in parts of the
   file the user isn't invoking right now are deliberately ignored. Accepted
   cost: the reachability traversal runs on *unvalidated* dicts, so it keeps a
   small permanent set of defensive shape checks (task names and `deps` shape)
   with good bespoke errors. `--list`/`--show`/`--tree` have no root task, so
   they skip pruning and effectively validate the whole file.
3. **The merged-tree schema is generated on the fly** from the user-facing file
   schema: load the JSON, rewrite the name-key patterns (`^[^.]+$` →
   `^[^.]+(\.[^.]+)*$` and the `^(?!default$)…` variants likewise), and
   **forbid the `imports` key** (imports are consumed by the merge; their
   presence in the merged tree indicates a merge bug). A unit test must assert
   the transform rewrote the expected number of patterns, so schema edits that
   would silently break the transform fail tests instead.
4. **Runner/interpreter templates are restricted** to `var.*`, `env.*`, and the
   global `tt.*` builtins (`project_root`, `recipe_dir`, `user_home`,
   `user_name`). Forbidden: `arg.*`, `dep.*`, `self.*`, and per-task `tt.*`
   (`task_name`, `working_dir`). Enforced by a Python parse-time check (not a
   schema `not`/`pattern`) so the error can explain *why*: runners are shared
   across tasks, so per-task values aren't available. This is what makes
   one-shot runner rendering (step 7) sound, and matches de-facto v1.3.2
   behaviour (the old regex path never supported `arg.*` in runner fields).
5. **Hashing uses unrendered template strings PLUS the resolved values of every
   `var.*` and `env.*` the task references** (volatile builtins like
   `tt.timestamp` excluded). Hashing values-not-templates covers
   `eval:`/`read:`/env-sourced indirection automatically: however a value was
   produced, if it changed, the hash changes. Two consequences to preserve:
   - Today `var.*` is substituted at parse time, so variable values are
     implicitly baked into the hashed `cmd` — a naive "hash the unrendered
     fields" would silently *lose* variable-change detection. The referenced
     values in the hash restore it. Write the "variable value change triggers
     re-run" test **early** — nothing else catches this regression.
   - Including `env.*` values is a deliberate behaviour change: v1.3.2 never
     re-runs on env-var changes (e.g. `PYTHONPATH`). Only *referenced* env vars
     count — implicit environment inheritance still doesn't trigger re-runs.
     The contract is "if your task depends on an env var, reference it" (a
     future `sensitive_to:` field could cover vars that matter but don't appear
     in command text — out of scope here).
6. **Requirement discovery via a single generic walker**:
   `collect_template_refs(raw_subtree) -> {prefix: set[names]}` traverses every
   string in a node's dict/list subtree — tasks/runners/interpreters each point
   it at their sub-dict. No enumerated field list, so new fields can't be
   silently missed. The same function serves pruning (which variables to
   evaluate), hashing (which values to fold in), and the decision-4 restriction
   (reject forbidden prefixes in runner subtrees) — sharing one implementation
   makes pruning/hashing disagreement structurally impossible. Bias extraction
   toward **over-matching**: evaluating an extra variable is harmless; missing
   one breaks rendering or hashing. Take the transitive closure over variable
   definitions (`var.a`'s definition may reference `var.b` or `env.X`);
   existing variable-cycle detection guards termination.

## 3. Process decisions

- **Error wording:** new. Wrap `jsonschema` errors in a friendly formatter
  (file, path, plain-English reason — raw `oneOf` failures are cryptic). Do
  **not** build a translation layer reproducing today's exact messages; the
  ~232 pinned tests are updated as each hand-written check migrates.
- **State reset:** the hash-input change invalidates every `.tasktree-state`
  entry, so all tasks re-run once after upgrade. Accepted; changelog note.
- **Branching:** all slices land on **one feature branch**, merged to `main`
  at the end. The branch is mergeable after slice 7 (double validation — schema
  plus not-yet-retired manual checks — is fine); slice 8 can trail.
- **Local commits:** per `CLAUDE.md`, Claude working locally never commits —
  each increment stops for user review and commit.

## 4. Reference arbiter

`main` at the start of this work is exactly the v1.3.2 release, and a git
worktree exists at `~/repos/tasktree-ref` pinned to tag `v1.3.2`
(commit `36de66d`, detached). `uv run tt …` there gives reference behaviour;
the source is readable and debuggable for "why does it do that" questions.

**Process rule:** when a behavioural divergence is discovered and *no existing
test pins it down*, reproduce it against the reference, write a
characterization test capturing the **old** behaviour, then consciously decide
keep-or-change. Never point both versions at the same project directory — they
fight over `.tasktree-state`, and the hash format differs after slice 7.

**Expected divergences** (intended, not regressions — grow this list as slices
land):

- env-var changes trigger re-runs (slice 7; v1.3.2 never re-runs on env change)
- validation error wording is new (slices 6/8)
- one-time full re-run after the hash format change (slice 7)
- `arg.*`/`dep.*`/`self.*`/per-task `tt.*` templates in runner or interpreter
  fields are rejected with an error (slice 3; v1.3.2 silently left most of
  these unsubstituted)
- broken-but-unreachable tasks are tolerated when invoking a specific task
  (slices 5/6; v1.3.2 errors on any parse-time-invalid task anywhere)

## 5. Slices

Dependency-ordered. Each slice is a run of small, individually-reviewable
increments (test + implementation per commit).

### Slice 0 — verifications (findings only, no code)
Confirm two assumptions empirically before building on them:
- `rendering.py`'s Jinja engine supports every template prefix the unified
  rendering path will need.
- No existing recipe/fixture/test uses `arg.*`/`dep.*`/`self.*` in runner
  fields (so slice 3's restriction breaks nothing).

### Slice 1 — unify rendering onto Jinja
Move docker runner field substitution (`volumes`, `ports`, `env_vars`,
container `working_dir`) off the old regex path (in `executor.py`) onto
`rendering.py`'s Jinja engine — one field + test per commit; delete the regex
path last. Independently valuable (fixes the `arg.*`-unsupported inconsistency
for task-level fields) and a prerequisite for one-mechanism rendering.

### Slice 2 — the reference walker
Build `collect_template_refs` (decision 6) plus the variable-definition
transitive closure. Purely additive — nothing calls it yet. Unit tests cover
all prefixes, nested dicts/lists, Jinja expressions (`{{ var.a if flag else
var.b }}`), and closure/cycle behaviour. Start with regex extraction
(over-matching is safe); a Jinja-AST upgrade can come later if fidelity needs
it.

### Slice 3 — runner variable-class restriction
Parse-time check (uses the walker) rejecting forbidden prefixes in runner and
interpreter subtrees, with the "runners are shared across tasks" explanation
in the error.

### Slice 4 — raw-dict merge phase *(the big one)*
Restructure `parser.py` so imports merge into one raw dict **before** any
`Task`/`Runner` object is constructed (today `_parse_file_with_env` recursively
builds objects with validation interleaved, and only the main file's raw dict
is retained). Namespacing, `run_in`, and pin rewrites become dict transforms.
Build the new path additively alongside the old one and cut over one section at
a time — runners first (most isolated) — deleting the old path when nothing
uses it.

### Slice 5 — reachability + pruning over raw dicts
Reimplement reachability over the merged dict (today `collect_reachable_tasks`
walks constructed `Task` objects): `deps` including parameterized syntax, with
the decision-2 defensive shape checks. Extend pruning to runners/interpreters
(new capability — today all are always parsed). `--list`/`--show`/`--tree`
skip pruning.

### Slice 6 — schema wiring
Three parts, in order:
1. Loosen the typed-templatable fields in `schema/tasktree-schema.json` per
   decision 1.
2. The merged-tree schema generator per decision 3, with its pattern-count
   regression test.
3. Wire `jsonschema.validate()` in post-prune (promote `jsonschema` from the
   `dev` extra to a runtime dependency), additively — no manual checks removed
   yet — behind the friendly error formatter.

### Slice 7 — hash change
Hash becomes unrendered templates + referenced `var.*`/`env.*` values via the
walker (decision 5). **Tests first**: variable change → re-run; env change →
re-run; one env reference per rendered field type (cmd, working_dir,
inputs/outputs, runner preamble/volumes/env_vars). Changelog notes the
one-time state invalidation and the new env sensitivity.

### Slice 8 — retire hand-written checks *(long tail)*
One manual structural check deleted per commit, its pinned tests updated to
the new wording as each goes. Only checks now covered by the schema are
eligible; graph/lifecycle checks (§1) stay. This slice can trail after the
branch merges.

## 6. Rough sizing

Slices 0–3 are each comfortably a single working session; slice 4 is several
sessions and the main risk concentration; slices 5–7 are likely a session
each; slice 8 is piecemeal filler for spare capacity in any session.
