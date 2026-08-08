"""
Behaviour tests for Task construction from the merged raw tree
(schema pipeline slice 4, tasks cutover).

Self-contained (only v1.3.2-era symbols) so the whole file can be copied into
the reference worktree for the gate run - see docs/plans/
schema-validation-pipeline.md section 4.
"""

import tempfile
import unittest
from pathlib import Path

from tasktree.parser import parse_recipe


class TaskCutoverTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, relative_path: str, content: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_recipe_with_import(self) -> Path:
        recipe = self.write(
            "tt.yaml",
            "variables:\n"
            "  greeting: root-value\n"
            "imports:\n"
            "  - file: sub/tasks.yaml\n"
            "    as: sub\n"
            "tasks:\n"
            "  top:\n"
            "    deps: helper\n"
            "    cmd: echo top\n"
            "  helper:\n"
            "    cmd: echo help\n",
        )
        self.write(
            "sub/tasks.yaml",
            "variables:\n"
            "  greeting: imported-value\n"
            "tasks:\n"
            "  worker:\n"
            "    cmd: echo {{ var.greeting }}\n"
            "    args:\n"
            "      - msg: {default: nothing}\n"
            "  consumer:\n"
            "    deps:\n"
            "      - worker: {msg: '{{ var.greeting }}'}\n"
            "    cmd: echo consuming\n"
            "  boxed:\n"
            "    cmd: pwd\n"
            "    runner:\n"
            "      working_dir: '{{ var.greeting }}'\n",
        )
        return recipe


class TestImportedTaskParity(TaskCutoverTestCase):
    def test_imported_task_source_file_points_at_defining_file(self):
        recipe = self.write_recipe_with_import()
        recipe_obj = parse_recipe(recipe)
        self.assertEqual(recipe_obj.tasks["top"].source_file, str(recipe))
        self.assertEqual(
            recipe_obj.tasks["sub.worker"].source_file,
            str(self.root / "sub" / "tasks.yaml"),
        )

    def test_root_string_dep_is_normalised_to_list(self):
        recipe = self.write_recipe_with_import()
        recipe_obj = parse_recipe(recipe)
        self.assertEqual(recipe_obj.tasks["top"].deps, ["helper"])

    def test_var_refs_in_imported_cmd_resolve_to_imported_scope(self):
        recipe = self.write_recipe_with_import()
        recipe_obj = parse_recipe(recipe)
        self.assertEqual(recipe_obj.tasks["sub.worker"].cmd, "echo imported-value")


class TestImportedTaskVarRefDivergence(TaskCutoverTestCase):
    """
    Intended divergence from v1.3.2: the merge's generic var-reference walk
    rewrites every string in an imported task, so dependency-argument
    templates and inline runner definitions now resolve in the imported
    file's scope. v1.3.2 rewrote only an enumerated field list and left
    these pointing at root scope.
    """

    def test_var_refs_in_imported_dep_args_are_namespaced(self):
        recipe = self.write_recipe_with_import()
        recipe_obj = parse_recipe(recipe)
        self.assertEqual(
            recipe_obj.tasks["sub.consumer"].deps,
            [{"sub.worker": {"msg": "{{ var.sub.greeting }}"}}],
        )

    def test_var_refs_in_imported_inline_runner_resolve_to_imported_scope(self):
        recipe = self.write_recipe_with_import()
        recipe_obj = parse_recipe(recipe)
        runner = recipe_obj.runners["sub.boxed.__inline__"]
        # Variables are substituted during parse_recipe's eager evaluation;
        # the namespaced reference must have resolved to the imported value
        self.assertEqual(runner.working_dir, "imported-value")


if __name__ == "__main__":
    unittest.main()
