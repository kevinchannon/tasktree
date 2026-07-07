"""
Behaviour tests for unreachable-task tolerance (schema pipeline slice 5).

Invoking a task prunes the recipe to the tasks reachable from it before
construction, so defects in un-invoked tasks are ignored. Listing/showing
has no pruning and still validates the whole file. Self-contained (only
v1.3.2-era symbols) so the whole file can be copied into the reference
worktree for the gate run - see docs/plans/schema-validation-pipeline.md
section 4.
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


BROKEN_UNREACHABLE_RECIPE = """
tasks:
  good:
    cmd: echo good
  broken:
    desc: no cmd field at all
  mangled: just-a-string
"""


class ToleranceTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)
        self.addCleanup(os.chdir, self._original_cwd)

    def write_recipe(self, content: str) -> None:
        (self.project_root / "tasktree.yaml").write_text(content, encoding="utf-8")


class TestBrokenUnreachableTasksAreTolerated(ToleranceTestCase):
    """
    Divergence from v1.3.2: invoking a task no longer fails on defects in
    tasks it doesn't depend on (v1.3.2 parsed and validated every task).
    """

    def test_invoking_good_task_ignores_broken_task(self):
        self.write_recipe(BROKEN_UNREACHABLE_RECIPE)
        result = self.runner.invoke(app, ["good"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)

    def test_invoking_good_task_ignores_broken_imported_task(self):
        (self.project_root / "other.yaml").write_text(
            "tasks:\n"
            "  fine:\n"
            "    cmd: echo fine\n"
            "  broken:\n"
            "    desc: no cmd\n",
            encoding="utf-8",
        )
        self.write_recipe(
            "imports:\n"
            "  - file: other.yaml\n"
            "    as: other\n"
            "tasks:\n"
            "  good:\n"
            "    deps: [other.fine]\n"
            "    cmd: echo good\n"
        )
        result = self.runner.invoke(app, ["good"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)


BROKEN_UNUSED_RUNNER_RECIPE = """
runners:
  broken:
    type: containerised
    engine: docker
    dockerfile: does/not/exist/Dockerfile
tasks:
  good:
    cmd: echo good
"""


class TestBrokenUnusedRunnersAreTolerated(ToleranceTestCase):
    """
    Divergence from v1.3.2: invoking a task no longer builds (and so no
    longer validates) runners and interpreters that nothing in the run
    references.
    """

    def test_invoking_task_ignores_broken_unused_runner(self):
        self.write_recipe(BROKEN_UNUSED_RUNNER_RECIPE)
        result = self.runner.invoke(app, ["good"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)

    def test_invoking_task_ignores_broken_unused_interpreter(self):
        self.write_recipe(
            "interpreters:\n"
            "  broken:\n"
            "    cmd: 42\n"
            "tasks:\n"
            "  good:\n"
            "    cmd: echo good\n"
        )
        result = self.runner.invoke(app, ["good"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)


class TestOverridesAndUsedDefinitionsStillWork(ToleranceTestCase):
    def test_runner_override_by_otherwise_unused_runner_works(self):
        # Parity: --runner naming a runner no task references must survive
        self.write_recipe(
            "runners:\n"
            "  spare:\n"
            "    interpreter: bash\n"
            "tasks:\n"
            "  good:\n"
            "    cmd: echo good\n"
        )
        result = self.runner.invoke(
            app, ["--runner", "spare", "good"], env=self.env
        )
        self.assertEqual(result.exit_code, 0, result.output)

    def test_unknown_runner_override_still_errors(self):
        self.write_recipe("tasks:\n  good:\n    cmd: echo good\n")
        result = self.runner.invoke(
            app, ["--runner", "no-such-runner", "good"], env=self.env
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Runner not found", result.output)

    def test_interpreter_override_by_otherwise_unused_interpreter_works(self):
        self.write_recipe(
            "interpreters:\n"
            "  spare:\n"
            "    cmd: bash\n"
            "tasks:\n"
            "  good:\n"
            "    cmd: echo good\n"
        )
        result = self.runner.invoke(
            app, ["--interpreter", "spare", "good"], env=self.env
        )
        self.assertEqual(result.exit_code, 0, result.output)

    def test_broken_runner_used_by_invoked_task_still_errors(self):
        self.write_recipe(
            "runners:\n"
            "  broken:\n"
            "    type: containerised\n"
            "    engine: docker\n"
            "    dockerfile: does/not/exist/Dockerfile\n"
            "tasks:\n"
            "  good:\n"
            "    cmd: echo good\n"
            "    runner: broken\n"
        )
        result = self.runner.invoke(app, ["good"], env=self.env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Dockerfile not found", result.output)

    def test_broken_unused_runner_still_errors_on_list(self):
        self.write_recipe(BROKEN_UNUSED_RUNNER_RECIPE)
        result = self.runner.invoke(app, ["--list"], env=self.env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Dockerfile not found", result.output)


class TestValidationStillCoversWhatMatters(ToleranceTestCase):
    def test_broken_reachable_dep_still_errors(self):
        self.write_recipe(
            "tasks:\n"
            "  good:\n"
            "    deps: [broken]\n"
            "    cmd: echo good\n"
            "  broken:\n"
            "    desc: no cmd\n"
        )
        result = self.runner.invoke(app, ["good"], env=self.env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("missing required 'cmd'", result.output)

    def test_list_still_validates_whole_file(self):
        self.write_recipe(BROKEN_UNREACHABLE_RECIPE)
        result = self.runner.invoke(app, ["--list"], env=self.env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("missing required 'cmd'", result.output)

    def test_show_still_validates_whole_file(self):
        self.write_recipe(BROKEN_UNREACHABLE_RECIPE)
        result = self.runner.invoke(app, ["--show", "good"], env=self.env)
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("missing required 'cmd'", result.output)


if __name__ == "__main__":
    unittest.main()
