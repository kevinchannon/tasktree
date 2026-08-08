"""
Behaviour tests for name-aware state pruning (schema pipeline slice 5).

Targeted runs must not destroy the incremental state of tasks that merely
weren't invoked. Self-contained (only v1.3.2-era symbols) so the whole file
can be copied into the reference worktree for the gate run - see
docs/plans/schema-validation-pipeline.md section 4.
"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


RECIPE = """
variables:
  msg: hello
tasks:
  plain:
    cmd: echo plain
  varry:
    cmd: echo {{ var.msg }}
"""


class StatePruningTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        (self.project_root / "tasktree.yaml").write_text(RECIPE, encoding="utf-8")
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)
        self.addCleanup(os.chdir, self._original_cwd)

    def run_task(self, name: str) -> None:
        result = self.runner.invoke(app, [name], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)

    def state_entries(self) -> dict:
        with open(self.project_root / ".tasktree-state", "r") as f:
            return json.load(f)

    def state_task_names(self) -> set:
        return {
            entry.get("task_name", "") for entry in self.state_entries().values()
        }


class TestStateEntriesCarryTaskNames(StatePruningTestCase):
    def test_state_entry_records_task_name(self):
        """
        Divergence from v1.3.2: entries were anonymous (hash-keyed only),
        so pruning could not tell a stale entry from an un-invoked task's.
        """
        self.run_task("plain")
        self.assertEqual(self.state_task_names(), {"plain"})


class TestTargetedRunsPreserveOtherTasksState(StatePruningTestCase):
    def test_var_using_task_state_survives_other_task_run(self):
        """
        Divergence from v1.3.2 (bug fix): an un-invoked task whose fields
        use variables was hashed with its templates unsubstituted, so its
        state entry never matched and was pruned on every targeted run of
        another task.
        """
        self.run_task("varry")
        self.assertIn("varry", self.state_task_names())

        self.run_task("plain")
        self.assertEqual(self.state_task_names(), {"plain", "varry"})

    def test_deleted_task_state_is_still_pruned(self):
        """
        Parity: entries for tasks that no longer exist in the recipe are
        removed on the next run. (Asserted by entry count, not stored
        names, so the same probe runs against v1.3.2's nameless entries.)
        """
        self.run_task("varry")
        recipe_without_varry = (
            "variables:\n"
            "  msg: hello\n"
            "tasks:\n"
            "  plain:\n"
            "    cmd: echo plain\n"
        )
        (self.project_root / "tasktree.yaml").write_text(
            recipe_without_varry, encoding="utf-8"
        )
        self.run_task("plain")
        self.assertEqual(len(self.state_entries()), 1)


if __name__ == "__main__":
    unittest.main()
