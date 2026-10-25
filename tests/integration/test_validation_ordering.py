"""
Integration tests for what runs before a recipe is known to be valid.

Structural validation happens before variables are evaluated, and that
ordering is a security property rather than a detail: an ``eval:`` variable
is a shell command, so a recipe that does not even have a valid shape must
never get as far as running one.

Raised in the PR #212 review, which asked for the ordering to be pinned by
a test rather than left as a property of the pipeline's current shape.
"""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


class ValidationOrderingTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)
        self.addCleanup(lambda: os.chdir(self._original_cwd))
        self.sentinel = self.project_root / "eval-ran.txt"

    def write_recipe(self, text: str) -> None:
        (self.project_root / "tasktree.yaml").write_text(text)

    def run_build(self, *args: str):
        """Invoke tt, defaulting to running the task."""
        result = self.runner.invoke(
            app, list(args) or ["build"], env={"NO_COLOR": "1"}
        )
        return result, re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)

    def recipe(self, extra_task_field: str = "") -> str:
        """
        A recipe whose one variable runs a command that leaves a trace.

        ``touch`` is avoided: the command has to run on every platform the
        suite runs on, and a redirect is the one thing cmd.exe and a shell
        agree about.
        """
        return (
            "variables:\n"
            f'  probe: {{ eval: "echo ran > {self.sentinel.name}" }}\n'
            "tasks:\n"
            "  build:\n"
            "    cmd: echo {{ var.probe }}\n"
            f"{extra_task_field}"
        )


class TestEvalWaitsForAValidRecipe(ValidationOrderingTestCase):
    def test_a_structurally_invalid_recipe_runs_nothing(self):
        self.write_recipe(self.recipe("    not_a_field: anything\n"))

        result, output = self.run_build()

        self.assertNotEqual(result.exit_code, 0, output)
        self.assertFalse(
            self.sentinel.exists(),
            "an eval: variable ran although the recipe was not valid",
        )

    def test_a_valid_recipe_does_run_it(self):
        """The guard above would pass trivially if eval: never ran at all."""
        self.write_recipe(self.recipe())

        result, output = self.run_build()

        self.assertEqual(result.exit_code, 0, output)
        self.assertTrue(self.sentinel.exists(), output)


class TestEveryEntryPointWaitsTheSame(ValidationOrderingTestCase):
    """
    The commands that only *describe* a recipe take a different route: with
    no task to invoke they skip pruning, and they evaluate every variable
    rather than the reachable ones. So they are the paths most likely to
    reach an ``eval:`` early, and the guarantee has to hold on each of them
    (raised in the PR #212 review, which asked for exactly this).
    """

    def assert_nothing_ran(self, *args: str) -> None:
        self.write_recipe(self.recipe("    not_a_field: anything\n"))

        result, output = self.run_build(*args)

        self.assertNotEqual(result.exit_code, 0, output)
        self.assertFalse(
            self.sentinel.exists(),
            f"an eval: variable ran for {' '.join(args)} on an invalid recipe",
        )

    def test_list_runs_nothing(self):
        self.assert_nothing_ran("--list")

    def test_show_runs_nothing(self):
        self.assert_nothing_ran("--show", "build")

    def test_tree_runs_nothing(self):
        self.assert_nothing_ran("--tree", "build")


if __name__ == "__main__":
    unittest.main()
