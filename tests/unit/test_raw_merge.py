"""Unit tests for the raw-dict import merge (schema pipeline slice 4)."""

import tempfile
import unittest
from pathlib import Path

from tasktree.raw_merge import (
    CircularImportError,
    collect_reachable_task_names,
    merge_recipe,
    merge_recipe_files,
    prune_unreferenced_interpreters,
    prune_unreferenced_runners,
)


class RawMergeTestCase(unittest.TestCase):
    """Base: a temp directory to write recipe fixture files into."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path


class TestNoImports(RawMergeTestCase):
    def test_file_without_imports_round_trips(self):
        recipe = self.write(
            "tt.yaml",
            "tasks:\n"
            "  build:\n"
            "    cmd: make\n"
            "variables:\n"
            "  version: 1.2.3\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged,
            {
                "tasks": {"build": {"cmd": "make"}},
                "variables": {"version": "1.2.3"},
            },
        )

    def test_empty_file_merges_to_empty_dict(self):
        recipe = self.write("tt.yaml", "")
        self.assertEqual(merge_recipe(recipe), {})

    def test_comment_only_file_merges_to_empty_dict(self):
        recipe = self.write("tt.yaml", "# nothing here\n")
        self.assertEqual(merge_recipe(recipe), {})


class TestImportErrors(RawMergeTestCase):
    def test_missing_import_file_raises(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: nope.yaml\n"
            "    as: nope\n",
        )
        with self.assertRaises(FileNotFoundError) as cm:
            merge_recipe(recipe)
        self.assertIn("Import file not found", str(cm.exception))
        self.assertIn("nope.yaml", str(cm.exception))

    def test_self_import_raises_circular(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: tt.yaml\n"
            "    as: me\n",
        )
        with self.assertRaises(CircularImportError) as cm:
            merge_recipe(recipe)
        self.assertEqual(
            str(cm.exception), "Circular import detected: tt.yaml → tt.yaml"
        )

    def test_mutual_import_raises_circular_with_chain(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: other.yaml\n"
            "    as: other\n",
        )
        self.write(
            "other.yaml",
            "imports:\n"
            "  - file: tt.yaml\n"
            "    as: main\n",
        )
        with self.assertRaises(CircularImportError) as cm:
            merge_recipe(recipe)
        self.assertEqual(
            str(cm.exception),
            "Circular import detected: tt.yaml → other.yaml → tt.yaml",
        )

    def test_diamond_import_is_not_circular(self):
        # Two routes to the same file must not be mistaken for a cycle
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: left.yaml\n"
            "    as: left\n"
            "  - file: right.yaml\n"
            "    as: right\n",
        )
        self.write(
            "left.yaml",
            "imports:\n"
            "  - file: shared.yaml\n"
            "    as: shared\n",
        )
        self.write(
            "right.yaml",
            "imports:\n"
            "  - file: shared.yaml\n"
            "    as: shared\n",
        )
        self.write("shared.yaml", "tasks:\n  t:\n    cmd: echo\n")
        merge_recipe(recipe)  # Must not raise

    def test_imports_key_is_consumed(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: other.yaml\n"
            "    as: other\n"
            "tasks:\n"
            "  t:\n"
            "    cmd: echo\n",
        )
        self.write("other.yaml", "tasks:\n  o:\n    cmd: echo\n")
        merged = merge_recipe(recipe)
        self.assertNotIn("imports", merged)


class TestTaskMerging(RawMergeTestCase):
    def test_imported_tasks_are_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "tasks:\n"
            "  local:\n"
            "    cmd: echo local\n",
        )
        self.write(
            "build.yaml",
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["tasks"],
            {
                "build.compile": {"cmd": "make"},
                "local": {"cmd": "echo local"},
            },
        )

    def test_nested_imports_get_full_namespace_chain(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: a.yaml\n"
            "    as: a\n",
        )
        self.write(
            "a.yaml",
            "imports:\n"
            "  - file: b.yaml\n"
            "    as: b\n"
            "tasks:\n"
            "  mid:\n"
            "    cmd: echo mid\n",
        )
        self.write(
            "b.yaml",
            "tasks:\n"
            "  deep:\n"
            "    cmd: echo deep\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            set(merged["tasks"]),
            {"a.mid", "a.b.deep"},
        )

    def test_root_without_tasks_gains_imported_tasks(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write("build.yaml", "tasks:\n  compile:\n    cmd: make\n")
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"], {"build.compile": {"cmd": "make"}})

    def test_import_without_tasks_section_is_harmless(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: vars.yaml\n"
            "    as: v\n"
            "tasks:\n"
            "  local:\n"
            "    cmd: echo\n",
        )
        self.write("vars.yaml", "variables:\n  x: 1\n")
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"], {"local": {"cmd": "echo"}})

    def test_multiple_imports_all_merge(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: one.yaml\n"
            "    as: one\n"
            "  - file: two.yaml\n"
            "    as: two\n",
        )
        self.write("one.yaml", "tasks:\n  t:\n    cmd: echo 1\n")
        self.write("two.yaml", "tasks:\n  t:\n    cmd: echo 2\n")
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["tasks"],
            {"one.t": {"cmd": "echo 1"}, "two.t": {"cmd": "echo 2"}},
        )


class TestDepRewriting(RawMergeTestCase):
    def merged_task(self, imported_yaml: str, task_key: str) -> dict:
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write("build.yaml", imported_yaml)
        return merge_recipe(recipe)["tasks"][task_key]

    def test_simple_dep_gets_namespace_prefix(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "  link:\n"
            "    deps: [compile]\n"
            "    cmd: ld\n",
            "build.link",
        )
        self.assertEqual(task["deps"], ["build.compile"])

    def test_string_deps_value_is_normalised_and_prefixed(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "  link:\n"
            "    deps: compile\n"
            "    cmd: ld\n",
            "build.link",
        )
        self.assertEqual(task["deps"], ["build.compile"])

    def test_external_dotted_dep_is_kept_absolute(self):
        task = self.merged_task(
            "tasks:\n"
            "  link:\n"
            "    deps: [other.setup]\n"
            "    cmd: ld\n",
            "build.link",
        )
        self.assertEqual(task["deps"], ["other.setup"])

    def test_parameterized_dep_name_is_rewritten_args_preserved(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make {{ arg.mode }}\n"
            "    args:\n"
            "      - mode\n"
            "  link:\n"
            "    deps:\n"
            "      - compile:\n"
            "          mode: release\n"
            "    cmd: ld\n",
            "build.link",
        )
        self.assertEqual(task["deps"], [{"build.compile": {"mode": "release"}}])

    def test_dep_on_own_import_gets_full_chain(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: a.yaml\n"
            "    as: a\n",
        )
        self.write(
            "a.yaml",
            "imports:\n"
            "  - file: b.yaml\n"
            "    as: b\n"
            "tasks:\n"
            "  mid:\n"
            "    deps: [b.deep]\n"
            "    cmd: echo\n",
        )
        self.write("b.yaml", "tasks:\n  deep:\n    cmd: echo\n")
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"]["a.mid"]["deps"], ["a.b.deep"])

    def test_root_file_deps_are_untouched(self):
        recipe = self.write(
            "tt.yaml",
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "  link:\n"
            "    deps: [compile]\n"
            "    cmd: ld\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"]["link"]["deps"], ["compile"])


class TestRunnerTransforms(RawMergeTestCase):
    def merged_task(
        self, imported_yaml: str, task_key: str, run_in: str = ""
    ) -> dict:
        run_in_line = f"    run_in: {run_in}\n" if run_in else ""
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n" + run_in_line,
        )
        self.write("build.yaml", imported_yaml)
        return merge_recipe(recipe)["tasks"][task_key]

    def test_imported_task_runner_name_is_prefixed(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: docker\n",
            "build.compile",
        )
        self.assertEqual(task["runner"], "build.docker")

    def test_inline_runner_definition_is_untouched(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner:\n"
            "      interpreter: bash\n",
            "build.compile",
        )
        self.assertEqual(task["runner"], {"interpreter": "bash"})

    def test_run_in_applies_to_runnerless_task(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n",
            "build.compile",
            run_in="docker",
        )
        self.assertEqual(task["runner"], "docker")

    def test_run_in_does_not_override_named_runner(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: shell\n",
            "build.compile",
            run_in="docker",
        )
        self.assertEqual(task["runner"], "build.shell")

    def test_run_in_does_not_apply_to_pinned_task(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    pin_runner: true\n",
            "build.compile",
            run_in="docker",
        )
        self.assertNotIn("runner", task)

    def test_run_in_does_not_override_inline_runner(self):
        task = self.merged_task(
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner:\n"
            "      interpreter: bash\n",
            "build.compile",
            run_in="docker",
        )
        self.assertEqual(task["runner"], {"interpreter": "bash"})

    def test_run_in_does_not_cascade_to_nested_imports(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: a.yaml\n"
            "    as: a\n"
            "    run_in: docker\n",
        )
        self.write(
            "a.yaml",
            "imports:\n"
            "  - file: b.yaml\n"
            "    as: b\n"
            "tasks:\n"
            "  mid:\n"
            "    cmd: echo\n",
        )
        self.write("b.yaml", "tasks:\n  deep:\n    cmd: echo\n")
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"]["a.mid"]["runner"], "docker")
        self.assertNotIn("runner", merged["tasks"]["a.b.deep"])


class TestImportedRunners(RawMergeTestCase):
    PINNED_IMPORT = (
        "runners:\n"
        "  special:\n"
        "    interpreter: bash\n"
        "  unused:\n"
        "    interpreter: sh\n"
        "tasks:\n"
        "  compile:\n"
        "    cmd: make\n"
        "    runner: special\n"
        "    pin_runner: true\n"
        "  other:\n"
        "    cmd: echo\n"
        "    runner: unused\n"
    )

    def test_only_pinned_task_runners_are_imported(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write("build.yaml", self.PINNED_IMPORT)
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["runners"], {"build.special": {"interpreter": "bash"}}
        )

    def test_imported_default_declaration_is_dropped(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "runners:\n"
            "  default: shell\n"
            "  shell:\n"
            "    interpreter: bash\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  default: special\n"
            "  special:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["runners"],
            {
                "default": "shell",
                "shell": {"interpreter": "bash"},
                "build.special": {"interpreter": "bash"},
            },
        )

    def test_grandchild_pinned_runner_survives_to_root(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: a.yaml\n"
            "    as: a\n",
        )
        self.write(
            "a.yaml",
            "imports:\n"
            "  - file: b.yaml\n"
            "    as: b\n",
        )
        self.write(
            "b.yaml",
            "runners:\n"
            "  deep_runner:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  deep:\n"
            "    cmd: echo\n"
            "    runner: deep_runner\n"
            "    pin_runner: true\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["runners"], {"a.b.deep_runner": {"interpreter": "bash"}}
        )

    def test_import_without_runners_leaves_root_section_alone(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "runners:\n"
            "  shell:\n"
            "    interpreter: bash\n",
        )
        self.write("build.yaml", "tasks:\n  t:\n    cmd: echo\n")
        merged = merge_recipe(recipe)
        self.assertEqual(merged["runners"], {"shell": {"interpreter": "bash"}})

    def test_root_without_runners_gains_imported_pinned_runner(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write("build.yaml", self.PINNED_IMPORT)
        merged = merge_recipe(recipe)
        self.assertIn("build.special", merged["runners"])
        self.assertNotIn("build.unused", merged["runners"])


class TestVariableMerging(RawMergeTestCase):
    def test_imported_variable_keys_are_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "variables:\n"
            "  local_var: root\n",
        )
        self.write("build.yaml", "variables:\n  version: 1.2.3\n")
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["variables"],
            {"local_var": "root", "build.version": "1.2.3"},
        )

    def test_var_refs_in_imported_cmd_are_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  version: 1.2.3\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make VERSION={{ var.version }}\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["tasks"]["build.compile"]["cmd"],
            "make VERSION={{ var.build.version }}",
        )

    def test_var_refs_in_imported_variable_values_are_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  base: /opt\n"
            "  full: '{{ var.base }}/bin'\n"
            "  from_env:\n"
            "    env: BUILD_DIR\n"
            "    default: '{{ var.base }}/build'\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(merged["variables"]["build.full"], "{{ var.build.base }}/bin")
        self.assertEqual(
            merged["variables"]["build.from_env"],
            {"env": "BUILD_DIR", "default": "{{ var.build.base }}/build"},
        )

    def test_var_refs_in_parameterized_dep_args_are_namespaced(self):
        # Broader than the old object path, which never rewrote dep args
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  mode: release\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make {{ arg.mode }}\n"
            "    args:\n"
            "      - mode\n"
            "  link:\n"
            "    deps:\n"
            "      - compile:\n"
            "          mode: '{{ var.mode }}'\n"
            "    cmd: ld\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["tasks"]["build.link"]["deps"],
            [{"build.compile": {"mode": "{{ var.build.mode }}"}}],
        )

    def test_var_refs_in_imported_pinned_runner_are_namespaced(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "variables:\n"
            "  cache: /tmp/cache\n"
            "runners:\n"
            "  special:\n"
            "    interpreter: bash\n"
            "    volumes:\n"
            "      - '{{ var.cache }}:/cache'\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["runners"]["build.special"]["volumes"],
            ["{{ var.build.cache }}:/cache"],
        )

    def test_nested_import_vars_get_full_chain(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: a.yaml\n"
            "    as: a\n",
        )
        self.write(
            "a.yaml",
            "imports:\n"
            "  - file: b.yaml\n"
            "    as: b\n",
        )
        self.write(
            "b.yaml",
            "variables:\n"
            "  deep: x\n"
            "tasks:\n"
            "  t:\n"
            "    cmd: echo {{ var.deep }}\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(merged["variables"], {"a.b.deep": "x"})
        self.assertEqual(
            merged["tasks"]["a.b.t"]["cmd"], "echo {{ var.a.b.deep }}"
        )

    def test_root_var_refs_are_untouched(self):
        recipe = self.write(
            "tt.yaml",
            "variables:\n"
            "  version: 1.2.3\n"
            "tasks:\n"
            "  build:\n"
            "    cmd: make {{ var.version }}\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"]["build"]["cmd"], "make {{ var.version }}")


class TestInterpreterMerging(RawMergeTestCase):
    def test_imported_interpreters_are_namespaced_and_default_dropped(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "interpreters:\n"
            "  default: sh\n"
            "  sh: bash\n",
        )
        self.write(
            "build.yaml",
            "interpreters:\n"
            "  default: py\n"
            "  py:\n"
            "    cmd: python3\n"
            "    ext: .py\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["interpreters"],
            {
                "default": "sh",
                "sh": "bash",
                "build.py": {"cmd": "python3", "ext": ".py"},
            },
        )

    def test_imported_runner_use_ref_is_rewritten(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "interpreters:\n"
            "  py:\n"
            "    cmd: python3\n"
            "runners:\n"
            "  special:\n"
            "    interpreter:\n"
            "      use: py\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["runners"]["build.special"]["interpreter"],
            {"use": "build.py"},
        )
        self.assertIn("build.py", merged["interpreters"])

    def test_imported_task_interpreter_name_is_not_prefixed(self):
        # Task-level interpreter names resolve against the root registry
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "interpreters:\n"
            "  py:\n"
            "    cmd: python3\n",
        )
        self.write(
            "build.yaml",
            "tasks:\n"
            "  compile:\n"
            "    cmd: print('hi')\n"
            "    interpreter: py\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(merged["tasks"]["build.compile"]["interpreter"], "py")

    def test_inline_task_runner_use_ref_is_not_rewritten(self):
        # Inline task runner defs are materialised against the root
        # registry, so their use: refs must stay unprefixed
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "interpreters:\n"
            "  py:\n"
            "    cmd: python3\n",
        )
        self.write(
            "build.yaml",
            "tasks:\n"
            "  compile:\n"
            "    cmd: print('hi')\n"
            "    runner:\n"
            "      interpreter:\n"
            "        use: py\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["tasks"]["build.compile"]["runner"],
            {"interpreter": {"use": "py"}},
        )

    def test_string_interpreter_shorthand_passes_through(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  special:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  compile:\n"
            "    cmd: make\n"
            "    runner: special\n"
            "    pin_runner: true\n",
        )
        merged = merge_recipe(recipe)
        self.assertEqual(
            merged["runners"]["build.special"], {"interpreter": "bash"}
        )


class TestReachability(unittest.TestCase):
    """Reachability over the merged raw tasks dict (no Task objects)."""

    def test_root_alone_is_reachable(self):
        tasks = {"a": {"cmd": "x"}, "b": {"cmd": "y"}}
        self.assertEqual(collect_reachable_task_names(tasks, "a"), {"a"})

    def test_transitive_deps_are_reachable(self):
        tasks = {
            "a": {"cmd": "x", "deps": ["b"]},
            "b": {"cmd": "y", "deps": ["c"]},
            "c": {"cmd": "z"},
            "d": {"cmd": "unreached"},
        }
        self.assertEqual(
            collect_reachable_task_names(tasks, "a"), {"a", "b", "c"}
        )

    def test_string_deps_shorthand(self):
        tasks = {"a": {"cmd": "x", "deps": "b"}, "b": {"cmd": "y"}}
        self.assertEqual(collect_reachable_task_names(tasks, "a"), {"a", "b"})

    def test_parameterized_dict_dep(self):
        tasks = {
            "a": {"cmd": "x", "deps": [{"b": {"flag": 1}}]},
            "b": {"cmd": "y"},
        }
        self.assertEqual(collect_reachable_task_names(tasks, "a"), {"a", "b"})

    def test_dependency_cycle_terminates(self):
        tasks = {
            "a": {"cmd": "x", "deps": ["b"]},
            "b": {"cmd": "y", "deps": ["a"]},
        }
        self.assertEqual(collect_reachable_task_names(tasks, "a"), {"a", "b"})

    def test_missing_dep_is_kept_for_later_error(self):
        # Tolerance parity with the object-based traversal: a nonexistent
        # dep name stays in the set; graph construction reports it.
        tasks = {"a": {"cmd": "x", "deps": ["ghost"]}}
        self.assertEqual(
            collect_reachable_task_names(tasks, "a"), {"a", "ghost"}
        )

    def test_malformed_task_and_deps_are_tolerated(self):
        # Shape problems are deferred: a non-dict task is a leaf, non-list
        # deps and multi-key dep dicts contribute nothing. Construction and
        # graph building keep their existing errors for surviving tasks.
        tasks = {
            "a": {"cmd": "x", "deps": ["broken", "odd", "multi"]},
            "broken": "not-a-dict",
            "odd": {"cmd": "y", "deps": 42},
            "multi": {"cmd": "z", "deps": [{"p": [], "q": []}]},
            "p": {"cmd": "unreached"},
        }
        self.assertEqual(
            collect_reachable_task_names(tasks, "a"),
            {"a", "broken", "odd", "multi"},
        )


class TestRunnerPruning(unittest.TestCase):
    def test_unreferenced_runner_is_pruned(self):
        data = {
            "tasks": {"a": {"cmd": "x", "runner": "used"}},
            "runners": {"used": {"interpreter": "bash"}, "unused": {"bogus": 1}},
        }
        prune_unreferenced_runners(data, keep=())
        self.assertEqual(set(data["runners"]), {"used"})

    def test_default_runner_and_declaration_survive(self):
        data = {
            "tasks": {"a": {"cmd": "x"}},
            "runners": {"default": "fallback", "fallback": {}, "unused": {}},
        }
        prune_unreferenced_runners(data, keep=())
        self.assertEqual(set(data["runners"]), {"default", "fallback"})

    def test_keep_hint_protects_cli_override_runner(self):
        data = {
            "tasks": {"a": {"cmd": "x"}},
            "runners": {"cli-choice": {}, "unused": {}},
        }
        prune_unreferenced_runners(data, keep=("cli-choice",))
        self.assertEqual(set(data["runners"]), {"cli-choice"})

    def test_malformed_sections_are_left_alone(self):
        data = {"tasks": {"a": "not-a-dict"}, "runners": "bogus"}
        prune_unreferenced_runners(data, keep=())
        self.assertEqual(data["runners"], "bogus")


class TestInterpreterPruning(unittest.TestCase):
    def test_unreferenced_interpreter_is_pruned(self):
        data = {
            "tasks": {"a": {"cmd": "x", "interpreter": "used"}},
            "interpreters": {"used": {"cmd": "bash"}, "unused": {"cmd": 42}},
        }
        prune_unreferenced_interpreters(data, keep=())
        self.assertEqual(set(data["interpreters"]), {"used"})

    def test_default_declaration_and_target_survive(self):
        data = {
            "tasks": {"a": {"cmd": "x"}},
            "interpreters": {"default": "py", "py": {"cmd": "python3"}, "unused": {}},
        }
        prune_unreferenced_interpreters(data, keep=())
        self.assertEqual(set(data["interpreters"]), {"default", "py"})

    def test_use_refs_from_runners_and_inline_defs_survive(self):
        data = {
            "tasks": {
                "a": {
                    "cmd": "x",
                    "runner": {"interpreter": {"use": "from-inline-runner"}},
                },
                "b": {"cmd": "y", "interpreter": {"use": "from-task"}},
            },
            "runners": {"r": {"interpreter": {"use": "from-runner"}}},
            "interpreters": {
                "from-inline-runner": {"cmd": "a"},
                "from-task": {"cmd": "b"},
                "from-runner": {"cmd": "c"},
                "unused": {"cmd": "d"},
            },
        }
        prune_unreferenced_interpreters(data, keep=())
        self.assertEqual(
            set(data["interpreters"]),
            {"from-inline-runner", "from-task", "from-runner"},
        )

    def test_keep_hint_protects_cli_override_interpreter(self):
        data = {
            "tasks": {"a": {"cmd": "x"}},
            "interpreters": {"cli-choice": {"cmd": "z"}, "unused": {"cmd": "w"}},
        }
        prune_unreferenced_interpreters(data, keep=("cli-choice",))
        self.assertEqual(set(data["interpreters"]), {"cli-choice"})


class TestTopLevelKeyValidation(RawMergeTestCase):
    def test_unknown_top_level_key_raises(self):
        recipe = self.write(
            "tt.yaml",
            "bogus_section: 42\n"
            "tasks:\n"
            "  build:\n"
            "    cmd: make\n",
        )
        with self.assertRaises(ValueError) as cm:
            merge_recipe(recipe)
        message = str(cm.exception)
        self.assertIn("Unknown top-level keys: bogus_section", message)
        self.assertIn(str(recipe), message)

    def test_root_level_task_definitions_get_tasks_hint(self):
        recipe = self.write(
            "tt.yaml",
            "build:\n"
            "  cmd: make\n",
        )
        with self.assertRaises(ValueError) as cm:
            merge_recipe(recipe)
        message = str(cm.exception)
        self.assertIn("Task definitions must be under a top-level 'tasks:' key", message)
        self.assertIn("build", message)
        self.assertIn(str(recipe), message)

    def test_unknown_key_in_imported_file_names_that_file(self):
        child = self.write(
            "child.yaml",
            "wrong: {a: 1}\n"
            "tasks:\n"
            "  t:\n"
            "    cmd: true\n",
        )
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: child.yaml\n"
            "    as: sub\n",
        )
        with self.assertRaises(ValueError) as cm:
            merge_recipe(recipe)
        self.assertIn(str(child), str(cm.exception))

    def test_file_with_only_imports_is_valid(self):
        self.write("child.yaml", "tasks:\n  t:\n    cmd: true\n")
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: child.yaml\n"
            "    as: sub\n",
        )
        merged = merge_recipe(recipe)
        self.assertIn("sub.t", merged["tasks"])


class TestLocalTaskNameValidation(RawMergeTestCase):
    """Task names raise during the merge (runners/variables defer instead)."""

    def test_root_task_name_with_dots_raises(self):
        recipe = self.write(
            "tt.yaml",
            "tasks:\n"
            "  build.release:\n"
            "    cmd: make\n",
        )
        with self.assertRaises(ValueError) as cm:
            merge_recipe(recipe)
        self.assertEqual(
            str(cm.exception),
            "Task name 'build.release' must not contain dots "
            "(reserved for import namespacing)",
        )

    def test_imported_task_name_with_dots_raises(self):
        self.write(
            "child.yaml",
            "tasks:\n"
            "  a.b:\n"
            "    cmd: true\n",
        )
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: child.yaml\n"
            "    as: sub\n",
        )
        with self.assertRaises(ValueError) as cm:
            merge_recipe(recipe)
        self.assertIn("Task name 'a.b' must not contain dots", str(cm.exception))

    def test_empty_task_name_raises(self):
        recipe = self.write(
            "tt.yaml",
            "tasks:\n"
            "  '':\n"
            "    cmd: true\n",
        )
        with self.assertRaises(ValueError) as cm:
            merge_recipe(recipe)
        self.assertEqual(str(cm.exception), "Task name must not be empty")


class TestTaskProvenance(RawMergeTestCase):
    def test_root_tasks_map_to_root_file(self):
        recipe = self.write(
            "tt.yaml",
            "tasks:\n"
            "  build:\n"
            "    cmd: make\n",
        )
        merged = merge_recipe_files(recipe)
        self.assertEqual(merged.task_sources, {"build": str(recipe)})

    def test_imported_tasks_map_to_their_file(self):
        child = self.write(
            "sub/child.yaml",
            "tasks:\n"
            "  compile:\n"
            "    cmd: cc\n",
        )
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: sub/child.yaml\n"
            "    as: sub\n"
            "tasks:\n"
            "  build:\n"
            "    cmd: make\n",
        )
        merged = merge_recipe_files(recipe)
        self.assertEqual(
            merged.task_sources,
            {"build": str(recipe), "sub.compile": str(child)},
        )

    def test_nested_import_tasks_map_to_leaf_file(self):
        leaf = self.write(
            "a/b/leaf.yaml",
            "tasks:\n"
            "  deep:\n"
            "    cmd: true\n",
        )
        self.write(
            "a/mid.yaml",
            "imports:\n"
            "  - file: b/leaf.yaml\n"
            "    as: inner\n",
        )
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: a/mid.yaml\n"
            "    as: outer\n",
        )
        merged = merge_recipe_files(recipe)
        self.assertEqual(merged.task_sources, {"outer.inner.deep": str(leaf)})


class TestNameErrorCollection(RawMergeTestCase):
    def test_clean_recipe_has_no_name_errors(self):
        recipe = self.write(
            "tt.yaml",
            "runners:\n"
            "  shell:\n"
            "    interpreter: bash\n"
            "variables:\n"
            "  ok: yes\n"
            "tasks:\n"
            "  t:\n"
            "    cmd: echo\n",
        )
        self.assertEqual(merge_recipe_files(recipe).name_errors, {})

    def test_root_runner_with_dots_gets_deferred_error(self):
        recipe = self.write(
            "tt.yaml",
            "runners:\n"
            "  bad.name:\n"
            "    interpreter: bash\n",
        )
        errors = merge_recipe_files(recipe).name_errors
        self.assertEqual(
            errors,
            {
                "bad.name": "Runner name 'bad.name' must not contain dots "
                "(reserved for import namespacing)"
            },
        )

    def test_imported_runner_error_is_keyed_by_merged_name(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  bad.name:\n"
            "    interpreter: bash\n",
        )
        errors = merge_recipe_files(recipe).name_errors
        self.assertIn("build.bad.name", errors)
        self.assertIn("'bad.name'", errors["build.bad.name"])

    def test_imported_variable_error_is_keyed_by_merged_name(self):
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write("build.yaml", "variables:\n  bad.var: x\n")
        errors = merge_recipe_files(recipe).name_errors
        self.assertIn("build.bad.var", errors)
        self.assertIn("'bad.var'", errors["build.bad.var"])

    def test_unimported_runner_still_gets_name_error(self):
        # Selective import drops non-pinned runners from the tree, but a
        # non-pinned task can still name one - the deferred error must
        # exist for the reachability check to find
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n",
        )
        self.write(
            "build.yaml",
            "runners:\n"
            "  bad.name:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  t:\n"
            "    cmd: echo\n"
            "    runner: bad.name\n",
        )
        merged = merge_recipe_files(recipe)
        self.assertNotIn("build.bad.name", merged.data.get("runners", {}))
        self.assertIn("build.bad.name", merged.name_errors)

    def test_default_keys_are_not_name_validated(self):
        recipe = self.write(
            "tt.yaml",
            "runners:\n"
            "  default: shell\n"
            "  shell:\n"
            "    interpreter: bash\n"
            "interpreters:\n"
            "  default: sh\n"
            "  sh: bash\n",
        )
        self.assertEqual(merge_recipe_files(recipe).name_errors, {})


class TestParseRecipeMirrorsMergedTree(RawMergeTestCase):
    """
    parse_recipe now builds on the merge, so this is no longer a parity
    check between two paths (its original slice-4 cutover role). It stays
    as a consistency check: the Recipe's Task objects and registries must
    faithfully reflect the merged dict - construction must not drop,
    rename or transform anything the merge already settled.
    """

    def build_fixture(self) -> Path:
        recipe = self.write(
            "tt.yaml",
            "imports:\n"
            "  - file: build.yaml\n"
            "    as: build\n"
            "    run_in: docker\n"
            "runners:\n"
            "  default: docker\n"
            "  docker:\n"
            "    interpreter: bash\n"
            "variables:\n"
            "  root_var: hello\n"
            "tasks:\n"
            "  all:\n"
            "    deps: [build.link]\n"
            "    cmd: echo {{ var.root_var }}\n",
        )
        self.write(
            "build.yaml",
            "imports:\n"
            "  - file: common.yaml\n"
            "    as: common\n"
            "runners:\n"
            "  special:\n"
            "    interpreter: bash\n"
            "variables:\n"
            "  mode: release\n"
            "tasks:\n"
            "  compile:\n"
            "    deps: [common.setup]\n"
            "    cmd: make {{ var.mode }}\n"
            "    runner: special\n"
            "    pin_runner: true\n"
            "  link:\n"
            "    deps: [compile]\n"
            "    cmd: ld\n",
        )
        self.write(
            "common.yaml",
            "variables:\n"
            "  prefix: /opt\n"
            "tasks:\n"
            "  setup:\n"
            "    cmd: mkdir -p {{ var.prefix }}\n",
        )
        return recipe

    def test_task_names_match_parse_recipe(self):
        from tasktree.parser import parse_recipe

        recipe_path = self.build_fixture()
        merged = merge_recipe(recipe_path)
        recipe = parse_recipe(recipe_path)
        self.assertEqual(set(merged["tasks"]), set(recipe.tasks))

    def test_runner_names_match_parse_recipe(self):
        from tasktree.parser import parse_recipe

        recipe_path = self.build_fixture()
        merged = merge_recipe(recipe_path)
        recipe = parse_recipe(recipe_path)
        merged_runner_names = set(merged["runners"]) - {"default"}
        self.assertEqual(merged_runner_names, set(recipe.runners))
        self.assertEqual(merged["runners"]["default"], recipe.default_runner)

    def test_variable_names_match_parse_recipe(self):
        from tasktree.parser import parse_recipe

        recipe_path = self.build_fixture()
        merged = merge_recipe(recipe_path)
        recipe = parse_recipe(recipe_path)
        self.assertEqual(set(merged["variables"]), set(recipe.raw_variables))

    def test_task_fields_match_parse_recipe(self):
        from tasktree.parser import parse_recipe

        recipe_path = self.build_fixture()
        merged = merge_recipe(recipe_path)
        recipe = parse_recipe(recipe_path)
        for name, task in recipe.tasks.items():
            merged_task = merged["tasks"][name]
            self.assertEqual(merged_task.get("deps", []), task.deps, name)
            self.assertEqual(merged_task.get("runner", ""), task.runner, name)
            self.assertEqual(
                merged_task.get("pin_runner", False), task.pin_runner, name
            )


if __name__ == "__main__":
    unittest.main()
