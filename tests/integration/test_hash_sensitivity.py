"""
Integration tests for what a task's hash is sensitive to (schema pipeline
slice 7, decision 5).

A task re-runs when anything it depends on changes. Command text and inputs
are the obvious cases; these cover the indirect ones -- the values behind the
``var.*`` and ``env.*`` references in a task's definition, whichever way the
value was produced (literal, ``env:``, ``eval:``, ``read:``).

The variable case is the regression net the plan calls for first: variable
values are baked into the command at parse time today, so a hash built from
unrendered templates would silently stop noticing variable edits.

Self-contained (only v1.3.2-era symbols) so the file can be copied into the
reference worktree for the gate run.
"""

import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class HashSensitivityTestCase(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)
        self.addCleanup(lambda: os.chdir(self._original_cwd))
        # Tasks with no inputs always re-run, which would mask every freshness
        # question these tests ask. Written once: rewriting it would bump its
        # mtime and re-run the task for that reason instead of the one under
        # test.
        (self.project_root / "src.txt").write_text("source\n")

    def write_recipe(self, text: str) -> None:
        (self.project_root / "tasktree.yaml").write_text(text)

    def run_task(self, task: str = "build", env: dict | None = None):
        result = self.runner.invoke(
            app, [task], env={"NO_COLOR": "1", **(env or {})}
        )
        return result, strip_ansi_codes(result.stdout)

    def assert_ran(self, output: str, result) -> None:
        """A task that executes announces itself; a fresh one stays quiet."""
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("Running: build", output)

    def assert_skipped(self, output: str, result) -> None:
        self.assertEqual(result.exit_code, 0, output)
        self.assertNotIn("Running: build", output)


class TestVariableChangesTriggerReruns(HashSensitivityTestCase):
    """
    The net the plan asks for first: nothing else catches a hash that stops
    tracking variable values.
    """

    def test_literal_variable_change_reruns(self):
        self.write_recipe(
            "variables:\n  greeting: hello\n"
            "tasks:\n  build:\n    inputs: [src.txt]\n    outputs: [out.txt]\n"
            "    cmd: echo {{ var.greeting }} > out.txt\n"
        )
        result, output = self.run_task()
        self.assert_ran(output, result)

        result, output = self.run_task()
        self.assert_skipped(output, result)

        self.write_recipe(
            "variables:\n  greeting: goodbye\n"
            "tasks:\n  build:\n    inputs: [src.txt]\n    outputs: [out.txt]\n"
            "    cmd: echo {{ var.greeting }} > out.txt\n"
        )
        result, output = self.run_task()
        self.assert_ran(output, result)

    def test_unreferenced_variable_change_does_not_rerun(self):
        """Only what the task actually references counts."""

        def recipe(unused_value: str) -> str:
            return (
                f"variables:\n  greeting: hello\n  unused: {unused_value}\n"
                "tasks:\n  build:\n    inputs: [src.txt]\n    outputs: [out.txt]\n"
                "    cmd: echo {{ var.greeting }} > out.txt\n"
            )

        self.write_recipe(recipe("one"))
        result, output = self.run_task()
        self.assert_ran(output, result)

        self.write_recipe(recipe("two"))
        result, output = self.run_task()
        self.assert_skipped(output, result)

    def test_eval_variable_value_change_reruns(self):
        """However the value was produced: here, a command's output."""
        source = self.project_root / "version.txt"
        source.write_text("1.0\n")
        self.write_recipe(
            "variables:\n  version: { eval: \"cat version.txt\" }\n"
            "tasks:\n  build:\n    inputs: [src.txt]\n    outputs: [out.txt]\n"
            "    cmd: echo {{ var.version }} > out.txt\n"
        )
        result, output = self.run_task()
        self.assert_ran(output, result)

        result, output = self.run_task()
        self.assert_skipped(output, result)

        source.write_text("2.0\n")
        result, output = self.run_task()
        self.assert_ran(output, result)


class TestEnvChangesTriggerReruns(HashSensitivityTestCase):
    """
    New in slice 7: a referenced env var's value is part of the hash.
    Implicit environment inheritance still is not -- the contract is that a
    task which depends on an env var references it.
    """

    def test_unreferenced_env_change_does_not_rerun(self):
        self.write_recipe(
            "tasks:\n  build:\n    inputs: [src.txt]\n    outputs: [out.txt]\n"
            "    cmd: echo hello > out.txt\n"
        )
        result, output = self.run_task(env={"TT_UNRELATED": "one"})
        self.assert_ran(output, result)

        result, output = self.run_task(env={"TT_UNRELATED": "two"})
        self.assert_skipped(output, result)

    def test_env_sourced_variable_change_reruns(self):
        """A var whose value comes from the environment, not a direct ref."""
        self.write_recipe(
            "variables:\n  target: { env: TT_TARGET, default: dev }\n"
            "tasks:\n  build:\n    inputs: [src.txt]\n    outputs: [out.txt]\n"
            "    cmd: echo {{ var.target }} > out.txt\n"
        )
        result, output = self.run_task(env={"TT_TARGET": "dev"})
        self.assert_ran(output, result)

        result, output = self.run_task(env={"TT_TARGET": "dev"})
        self.assert_skipped(output, result)

        result, output = self.run_task(env={"TT_TARGET": "prod"})
        self.assert_ran(output, result)


if __name__ == "__main__":
    unittest.main()
