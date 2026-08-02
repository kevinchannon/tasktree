# Implementation plan: runtime schema validation pipeline

> **Status:** in progress — slices 0–5 done plus slice 6 part 1 (see per-slice
> notes); next is slice 6 part 2 (the merged-tree schema generator). Branch
> `schema-validation-pipeline`; local commits are ahead of the pushed branch
> (a rebase onto newer `main` plus slice-6 work), so the next push is a
> force-push and [PR #212](https://github.com/kevinchannon/tasktree/pull/212)
> is stale until then.
> **Tracking issue:** [#43](https://github.com/kevinchannon/tasktree/issues/43).
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
- **Local commits:** Kevin has granted per-increment local commits for this
  work (supersedes `CLAUDE.md`'s never-commit rule); pushing still needs his
  explicit go-ahead.
- **Test bar before a push / slice completion:** all three suites — unit,
  integration, **and e2e** — must pass, not just the affected tests
  (Kevin's requirement, 2026-07-03). Per-increment runs of the affected
  tests remain the working rhythm; the full pyramid gates the push.

## 4. Reference arbiter

`main` at the start of this work is exactly the v1.3.2 release, and a git
worktree exists at `~/repos/tasktree-ref` pinned to tag `v1.3.2`
(commit `36de66d`, detached). `uv run tt …` there gives reference behaviour;
the source is readable and debuggable for "why does it do that" questions.

**The reference gates every increment — it is not only for disputes.** Before
declaring any change ready for review and commit:

1. Run the affected tests in the dev tree as usual.
2. Run every new or materially changed **behaviour-level** test against the
   reference: copy the test file(s) into the reference worktree, run just
   those tests there (`uv run --extra dev python -m pytest <files>`), then
   restore the worktree to pristine (`git checkout -- . && git clean -fd` in
   `~/repos/tasktree-ref`). Behaviour-level means integration/e2e tests and
   any unit test of pre-existing behaviour. Only tests of genuinely new
   internals with no v1.3.2 counterpart (e.g. the walker's own unit tests)
   are exempt — anything a user could observe through `tt` is never "new
   internals".
3. Record the verdict:
   - Reference **passes** → parity confirmed for that behaviour; proceed.
   - Reference **fails** → the test encodes a divergence. It must correspond
     to an entry in the expected-divergences list below (if it is a
     newly-intended divergence, add it to the list in the same increment).
     Otherwise **stop**: reproduce against the reference, write a
     characterization test capturing the **old** behaviour, and make a
     conscious keep-or-change decision before anything is committed.

The point is that parity evidence is collected continuously, increment by
increment — by the time the branch merges, every behaviour-level test in the
suite has a recorded verdict against v1.3.2, rather than the reference having
been consulted only when something felt dicey.

Never point both versions at the same project directory — they fight over
`.tasktree-state`, and the hash format differs after slice 7. Run comparisons
in separate copies of a fixture directory.

**Gate practicalities learned in slices 2–3:**

- Write behaviour tests destined for the gate in **self-contained files**
  (importing only v1.3.2-era symbols like `parse_recipe`), so a single file
  copies cleanly into the reference worktree. Tests of new internals can't
  even import there — keep them in separate files/classes.
- Make gate recipes **valid apart from the behaviour under test**, or the
  reference fails for the wrong reason and the verdict is contaminated.
  Concretely: v1.3.2 validates `dockerfile:`/`context:` paths on disk at
  parse time, so a gate fixture must create a real `docker/Dockerfile`; and
  a template in the `dockerfile:` field itself never parsed in v1.3.2 (path
  check), so templates under test belong in non-path-validated fields
  (volumes, env_vars, ports…). The clean divergence signature for a
  new-rejection test is exactly `AssertionError: ValueError not raised`.
- Restore with `git checkout -- . && git clean -fd` in `~/repos/tasktree-ref`
  and confirm `git status --porcelain` is empty before recording verdicts.

**Expected divergences** (intended, not regressions — grow this list as slices
land):

- env-var changes trigger re-runs (slice 7; v1.3.2 never re-runs on env change)
- validation error wording is new (slices 6/8)
- one-time full re-run after the hash format change (slice 7)
- `arg.*`/`dep.*`/`self.*` templates in runner or interpreter fields are
  rejected with an error (v1.3.2 silently left these unsubstituted, producing
  e.g. broken mount paths). Arrives field-by-field as slice 1 migrates each
  field onto Jinja's strict renderer (generic "undefined variable" wording);
  slice 3 makes it a parse-time check with an explanatory message.
- per-task `tt.*` builtins (`task_name`, `working_dir`, `timestamp`,
  `timestamp_unix`) in runner or interpreter fields are rejected at parse time
  (slice 3, decision 4; v1.3.2 rendered them per task at execution — only the
  four global builtins `project_root`/`recipe_dir`/`user_home`/`user_name`
  remain valid there)
- broken-but-unreachable tasks are tolerated when invoking a specific task
  (slices 5/6; v1.3.2 errors on any parse-time-invalid task anywhere —
  landed in slice 5, gate verdicts in
  `tests/integration/test_unreachable_task_tolerance.py`; `--list`/
  `--show`/`--tree` still validate the whole file)
- state entries carry their task's name, and targeted runs no longer prune
  the state of tasks that merely weren't invoked (slice 5 prerequisite;
  fixes a v1.3.2 bug where any un-invoked task using variables was hashed
  with its templates unsubstituted and its state thrashed on every run of
  another task — gate verdicts in `tests/integration/test_state_pruning.py`.
  Entries written by older versions carry no name and are pruned under the
  old hash-only rule once, i.e. a one-time re-run of un-invoked var-using
  tasks after upgrade)
- var-references in imported dep-argument templates and inline
  runner/interpreter definitions resolve in the imported file's scope
  (slice 4 tasks cutover; the merge's generic var-ref walk rewrites every
  string in an imported task, where v1.3.2 rewrote only an enumerated field
  list and left these pointing at root scope — gate verdicts recorded in
  `tests/unit/test_task_merge_cutover.py`)
- variable discovery is walker-based and over-matches (slice 5): every
  string in a reachable task's definition and its referenced runners'
  definitions is scanned, so variables v1.3.2's enumerated field list
  missed are now evaluated. Notably fixes a v1.3.2 bug where a variable
  referenced only by a non-Docker runner field (e.g. an inline host
  runner's working_dir) was never evaluated under lazy parsing and
  invocation failed with "Variable not defined" — gate verdicts in
  `tests/unit/test_variable_reachability.py`
- broken-but-unreferenced runners and interpreters are tolerated when
  invoking a specific task (slice 5; v1.3.2 built and validated every
  definition. The default runner/interpreter and CLI --runner/--interpreter
  override names always survive pruning; `--list`/`--show`/`--tree` still
  validate everything — gate verdicts in
  `tests/integration/test_unreachable_task_tolerance.py`)
- broken non-pinned imported runners are tolerated (slice 4 runners cutover;
  v1.3.2 eagerly built every imported file's runners — validating configs,
  Dockerfile paths, template restrictions — then discarded the non-pinned
  ones. The merged tree never contains them, so they are never built. A
  task referencing one still errors at reachability, as before.)

## 5. Slices

Dependency-ordered. Each slice is a run of small, individually-reviewable
increments (test + implementation per commit).

### Slice 0 — verifications (findings only, no code) ✅ done
Both assumptions confirmed (2026-07-03):
- **Jinja prefix coverage: yes.** `rendering.py` is namespace-agnostic — it
  renders whatever context it is given, and the two necessary rewrites already
  exist (`self` aliased around Jinja's reserved word; dotted `dep.` task names
  rewritten to subscript form). `task_config.build_task_config` supplies all
  six namespaces, with `env` defaulting to an `os.environ` snapshot.
- **No forbidden prefixes in runner fields: confirmed.** 471
  `arg.*`/`dep.*`/`self.*` template references exist across tests/fixtures,
  but zero occur inside `runners:`/`interpreters:`/inline `runner:` blocks
  (indentation-scoped scan, validated against planted positives). Slice 3's
  restriction breaks nothing.
- **Extra finding:** the regex runner-substitution path
  (`executor._substitute_builtin_in_runner`) covers more fields than this plan
  originally listed — see slice 1's expanded field list.

### Slice 1 — unify rendering onto Jinja ✅ done
Completed 2026-07-03: all runner/interpreter fields render through
`Executor._render_runner_field` (Jinja with the env+tt `build_runner_config`
context); the executor's regex wrappers are deleted. Every field has parity
coverage and an `arg.*`-rejection test; reference-gate verdicts recorded per
increment. Original scope follows.

Move runner field substitution off the old regex path
(`executor._substitute_builtin_in_runner`, which chains
`_substitute_builtin` for `tt.*` and `_substitute_env` for `env.*`) onto
`rendering.py`'s Jinja engine — one field + test per commit; delete the regex
helpers last. The full field list (wider than first assumed): `volumes`,
`ports`, `env_vars`, runner `working_dir`, `dockerfile`, `context`, docker
build/run `args`, and the runner's interpreter `cmd`/`preamble`. The Jinja
context for runner fields carries only `env` and `tt` (`var.*` was already
folded in at parse time; `arg.*`/`dep.*`/`self.*` are forbidden per decision
4). Independently valuable and a prerequisite for one-mechanism rendering.

### Slice 2 — the reference walker ✅ done
Completed 2026-07-03: `collect_template_refs` and `expand_variable_refs` live
in `src/tasktree/template_refs.py` with unit tests in
`tests/unit/test_template_refs.py`. Regex-based extraction as planned; dict
keys are walked too (over-matching bias). Reference gate: exempt — new
internals, no v1.3.2 counterpart. Original scope follows.

Build `collect_template_refs` (decision 6) plus the variable-definition
transitive closure. Purely additive — nothing calls it yet. Unit tests cover
all prefixes, nested dicts/lists, Jinja expressions (`{{ var.a if flag else
var.b }}`), and closure/cycle behaviour. Start with regex extraction
(over-matching is safe); a Jinja-AST upgrade can come later if fidelity needs
it.

### Slice 3 — runner variable-class restriction ✅ done
**Amended 2026-08-02:** `tt.uid`/`tt.gid` (added on `main` after this branch
was cut) joined the allowed set — they are host-global, resolved once per run
like `tt.user_name`, and the restriction was rejecting the canonical Docker
user-mapping recipe. Surfaced as four rebase-collision failures in
`tests/integration/test_builtin_variables.py`; one of those tests also pinned
the pre-slice-1 regex wording and now asserts the Jinja renderer's message.

Completed 2026-07-03: `check_runner_template_refs` in `parser.py` (uses the
slice-2 walker), called from `build_recipe_runner` (section + inline task
runners, including their `interpreter` fields) and
`_parse_inline_interpreter` (interpreters section + task-level inline
interpreters). Allowed `tt.*` names are exactly the four global builtins, so
`tt.timestamp`/`tt.timestamp_unix` are rejected alongside
`task_name`/`working_dir`. Behaviour tests live in
`tests/unit/test_runner_template_restriction.py` (self-contained for the
reference gate); gate verdicts: all six rejection tests fail on v1.3.2 with
"ValueError not raised" (recipes silently accepted — matches the
expected-divergences entries), both acceptance tests pass there. The
`builtin_vars_runner_volumes` fixture swapped its `tt.task_name` env var for
`tt.user_name`. Note: machine-config runners (`config.py` →
`runner_from_config`) are not covered — recipe-parse scope only; their
forbidden refs still fail at render via slice 1's strict Jinja. Original
scope follows.

Parse-time check (uses the walker) rejecting forbidden prefixes in runner and
interpreter subtrees, with the "runners are shared across tasks" explanation
in the error.

### Slice 4 — raw-dict merge phase *(the big one)* ✅ done
**Progress (2026-07-04, session 1):** the merge module is built and fully
unit-tested; no cutover yet (parse_recipe still runs the old object path
untouched, so nothing user-observable changed and the reference gate has not
been engaged).

- `src/tasktree/raw_merge.py` provides `merge_recipe(recipe_path) -> dict`:
  recursive import merge with circular/missing-file errors (message parity),
  task/runner/variable/interpreter namespacing, dep rewriting (incl. the
  local-import-namespace rule for dotted deps), task runner-name prefixing,
  `run_in` blanket, selective pinned-runner import, imported `default:` keys
  dropped, `imports` key consumed. Tests: `tests/unit/test_raw_merge.py`
  (47 tests), including a parity cross-check class against `parse_recipe`
  on a nested-import fixture — extend that class if cutover surfaces
  disagreements.
- `CircularImportError` and `VAR_REFERENCE_REWRITE_PATTERN` moved to
  `raw_merge.py`; `parser.py` imports them (import direction chosen so the
  eventual `parser -> raw_merge` dependency has no cycle).
- Var-ref namespacing is a **generic tree walk over values** (broader than
  the old enumerated field list): dep argument templates and inline
  runner/interpreter defs in imported files now get rewritten too. Add to
  expected divergences when the tasks cutover lands.
- Interpreter semantics preserved from the old path (verified in code):
  imported *runners* resolve `use:` against their own file's interpreters
  (merge rewrites the ref and keeps the namespaced interpreter); imported
  *tasks*' named interpreters and inline task-runner `use:` refs resolve
  against the **root** registry (left unprefixed). New tolerance: imported
  interpreters are now present (namespaced) in the merged tree instead of
  being discarded after runner construction.
**Progress (2026-07-04, session 2): runners, interpreters and variables are
cut over.** `_parse_file_with_env` now takes runners/interpreters (via
`_parse_runners_from_data` on the merged tree) and `raw_variables` straight
from `merge_recipe_files`; deferred name errors come from the merge
(`MergedRecipe.name_errors`, collected where local names are still visible
pre-namespacing — `local_name_error` lives in raw_merge, parser aliases it).
`_parse_file` now collects Task objects only (`ParsedFileResult` reduced to
`tasks`); deleted: `_extract_and_validate_runners`,
`_extract_and_validate_variables`, `_rewrite_runner_variable_references`,
`_rewrite_variable_references_in_raw_value`. Full pyramid green after each
cutover. Gate run for the runners cutover
(`tests/unit/test_runner_merge_cutover.py`, self-contained): 5 parity tests
pass on v1.3.2; the tolerance test fails there as intended (new
expected-divergences entry above). Variables cutover judged zero-divergence
(variable specs are strings/flat dicts, where the merge rewrite and the old
per-field rewrite coincide) — no new behaviour tests, existing suite is the
parity net.

**Progress (2026-07-05, session 3): tasks cut over — slice complete.**
`parse_recipe` now builds everything from one `merge_recipe_files` call:
`_build_tasks_from_merged` constructs Task objects from
`merged.data["tasks"]` (shape checks and
`_check_case_sensitive_arg_collisions` only — all cross-file transforms
are the merge's). Deleted: `_parse_file`, `_parse_file_with_env`,
`ParsedFileResult`, the per-field var-reference rewrite helpers, and
parser.py's direct YAML read (`import yaml` gone). Supporting merge work:
`MergedRecipe.task_sources` provenance (feeds `Task.source_file`),
per-file top-level-keys validation moved verbatim into `_merge_file`
(children validated before importer, matching old recursion order), and
local task names raise during the merge (runners/variables still defer).
`Recipe._original_yaml_data` is now `merged.data` — `_eval_interpreter`
only reads the runners/interpreters sections, whose root `default:` keys
survive the merge; imported interpreters became resolvable there as a
side benefit. Gate (`tests/unit/test_task_merge_cutover.py`,
self-contained): 3 parity tests pass on v1.3.2; the 2 divergence tests
(imported dep-argument templates, inline runner definitions — see
expected-divergences entry) fail there as intended. Full pyramid green.
Note for later: `TestParityWithObjectPath` in `test_raw_merge.py` is now
tautological (parse_recipe is merge-based) — repurpose or drop when
slice 5 touches that file.

Original scope follows.
Restructure `parser.py` so imports merge into one raw dict **before** any
`Task`/`Runner` object is constructed (today `_parse_file_with_env` recursively
builds objects with validation interleaved, and only the main file's raw dict
is retained). Namespacing, `run_in`, and pin rewrites become dict transforms.
Build the new path additively alongside the old one and cut over one section at
a time — runners first (most isolated) — deleting the old path when nothing
uses it.

**Handoff notes from the slice 2–3 session** (parser entry points verified
2026-07-03; find by name, line numbers drift):

- Runner construction is already well funnelled: the `runners:` section goes
  `_parse_runners_from_data` → `build_recipe_runner` → `runner_from_config`,
  and task-inline runners go `_materialise_inline_definitions` (registers
  them as `<task>.__inline__`) → `build_recipe_runner`. `build_recipe_runner`
  takes the **raw config dict**, which is what makes it the natural cutover
  seam for the runners-first migration.
- Interpreters likewise: `_parse_interpreters_section` and
  `parse_interpreter_spec` both bottom out in `_parse_inline_interpreter`
  (all in `parser.py`).
- Slice 3's `check_runner_template_refs` (parser.py) runs at the top of
  `build_recipe_runner` and `_parse_inline_interpreter` — the new merge path
  must keep calling it on raw definitions.
- The slice-2 walker lives in `src/tasktree/template_refs.py`
  (`collect_template_refs`, `expand_variable_refs`, `TEMPLATE_PREFIXES`).
  Slice 5 will use it to replace the Task-object-based
  `collect_reachable_tasks`/`collect_reachable_variables` (parser.py) —
  the latter's enumerated field list is exactly what the walker obsoletes.
- Not yet surveyed: the import-merge core itself (`_parse_file` /
  `_parse_file_with_env`, namespacing, `run_in`, pin rewrites). Start slice 4
  by reading those before writing anything.
- Don't forget the third runner kind: `NixRunner` (`type: nix`) exists in
  v1.3.2 and on this branch — `runner_from_config` has a `nix` branch
  (`nix_runner_from_config`), and `build_recipe_runner` validates flake
  paths on disk. The merge phase must carry it along like the other kinds
  (the §1/§2 prose predates it and only discusses host/containerised).

### Slice 5 — reachability + pruning over raw dicts ✅ done
Completed 2026-07-07 (session 4). What landed, in order:

- **Name-aware state pruning first** (discovered prerequisite, not in the
  original plan): `.tasktree-state` entries are hash-keyed with no task
  name, and `execute_dynamic_task` pruned state against the hashes of
  `recipe.tasks` — pruning tasks at parse would therefore have wiped
  un-invoked tasks' state on every targeted run. Worse, this thrash
  *already existed* in v1.3.2 for un-invoked tasks using variables (hashed
  with templates unsubstituted). Entries now carry `task_name`; the prune
  rule is: task gone from the recipe → removed, task in this run with a
  stale hash → removed, defined-but-not-invoked → kept, legacy nameless
  entries → old hash-only rule (one-time re-run for those after upgrade).
  `Recipe.defined_task_names` carries the pre-pruning universe. Gate:
  `tests/integration/test_state_pruning.py`.
- **Task pruning**: `parse_recipe(prune_unreachable=True)` — opt-in from
  `execute_dynamic_task` only — drops tasks unreachable from the root task
  (raw-dict traversal `collect_reachable_task_names` in `raw_merge.py`,
  same tolerance as the old object traversal: shape problems and missing
  deps defer to construction/graph errors). **Plan correction:** `--show`/
  `--tree` DO pass a root task (for lazy variable evaluation, incl. on
  v1.3.2), so pruning keys off the explicit flag, not off root_task —
  decision 2's "--list/--show/--tree have no root task" was wrong in that
  detail; its intent (those paths validate the whole file) holds. Gate:
  `tests/integration/test_unreachable_task_tolerance.py`.
- **Runner/interpreter pruning**: `prune_unreferenced_runners` /
  `prune_unreferenced_interpreters` (raw_merge) run after task pruning;
  `default` declarations + targets and `{use:}` refs from survivors are
  kept, and the CLI `--runner`/`--interpreter` override names thread
  through `get_recipe`/`parse_recipe` as keep-hints (an override naming an
  otherwise-unreferenced definition must survive — parity-tested).
- **Variable reachability via the slice-2 walker**: `evaluate_variables`
  computes the reachable set on the merged raw tree and discovers `var.*`
  refs with `collect_template_refs` over reachable task subtrees + their
  referenced runners (+ default). The object-based
  `collect_reachable_tasks`/`collect_reachable_variables` (enumerated
  field list) are deleted. Over-matching fixed a v1.3.2 bug (see
  expected-divergences). Gate: `tests/unit/test_variable_reachability.py`.

Note for slice 6: the eval-variable context `_original_yaml_data` is the
*pruned* merged tree on invocation paths — post-prune schema validation
can run on exactly that dict. Full pyramid green at slice end.

Original scope follows.
Reimplement reachability over the merged dict (today `collect_reachable_tasks`
walks constructed `Task` objects): `deps` including parameterized syntax, with
the decision-2 defensive shape checks. Extend pruning to runners/interpreters
(new capability — today all are always parsed). `--list`/`--show`/`--tree`
skip pruning.

### Slice 6 — schema wiring
Three parts, in order:
1. ✅ **Part 1 done (2026-08-02): the file schema now accepts everything the
   parser does.** Decision 1 assumed the loosening would be
   "native type OR a `{{…}}` string" for `min`/`max`, `ports`, docker build
   `args` and friends. **Correction: no such field exists.** Probing the
   parser (both this branch and v1.3.2) shows every typed field rejects
   templates outright, because each is consumed before any rendering:
   `min`/`max` (type-inferred as `str` → "does not match value types"),
   arg `type`, runner `type`/`engine`, `run_as_root`, interpreter `ext`
   (dot check). `ports`/`volumes`/docker `args` are already `string` in both
   schema and parser, so templates there always validated. The schema was
   therefore left narrow (`tests/unit/test_schema.py::
   TestTypedFieldsRejectTemplates` pins this, so nobody "implements
   decision 1" and loosens it below the parser).

   What the audit *did* find, and what landed:
   - **Bug:** `variables` listed `integer` and `number` as separate `oneOf`
     branches, so every integer value matched both and failed — `port: 8080`
     was rejected outright (4 fixtures hit it). Redundant branch removed.
   - A runner fixture carried a stray `default: true` key (silently ignored
     by the parser, rightly rejected by `additionalProperties: false`);
     dropped so it doesn't break when validation runs at parse time.
   - **Corpus test** (`TestFixtureCorpus`): all 355 recipes under
     `tests/fixtures` validate, bar an explicit allowlist of intentional
     negatives (currently just the dotted-task-name fixture). This is the
     regression net for parts 2–3 — verified it bites (an artificially
     stricter variables schema turns 1 rejection into 26).

   **Prospective divergences for part 3** — cases where the schema is
   *stricter* than the parser, so wiring validation turns them into new
   errors. Each is a silent-failure trap today and rejecting them is the
   point of the schema, but they need expected-divergences entries when
   part 3 lands: `desc: 42` and non-string `ports`/`volumes`/`env_vars`
   values (all TypeError'd in v1.3.2's regex path; slice 1's Jinja renderer
   passes non-strings through, so the branch currently tolerates them),
   and template strings in `private`/`pin_runner`/`task_output` (parsed
   today, never rendered — `private: "{{ var.f }}"` is simply always
   truthy). Note `task_output` is not converted to `TaskOutputTypes` at
   parse either (`parser.py`, `task_data.get("task_output")`) — worth a
   look while wiring part 3.

   Reference-gate verdict: the new schema tests pass on v1.3.2 except
   `test_integer_value_valid` (same schema bug there — an intended fix).
   The corpus test isn't gate-meaningful: v1.3.2 has a different fixture
   set and the schema file isn't consumed by `tt` at runtime in either
   version. **The reference worktree at `~/repos/tasktree-ref` had been
   deleted; recreated at `36de66d` (detached) — `git worktree prune` then
   `git worktree add … 36de66d --detach` if it goes missing again.**
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
