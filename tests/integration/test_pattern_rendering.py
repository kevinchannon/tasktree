"""
Integration tests for rendering templates in input and output patterns
(schema pipeline slice 10a).

A pattern has to be rendered before it is matched against the filesystem.
Until slice 10a that was done for ``{{ var.name }}`` only, and by a regex
pass at parse time rather than by the renderer -- so anything the regex
could not express (a filter, a conditional, an arithmetic expression) was
left in the pattern verbatim and silently matched nothing.

The failure that follows is quiet, which is why these are behavioural
tests rather than assertions about state: a task whose input pattern
matches no files has nothing to compare, so it runs once and is then
considered fresh for ever. The mirror case for outputs is noisy instead --
a pattern that never matches reports its outputs missing on every run --
so each is asserted in the direction it actually fails.

Deliberately NOT part of ``test_hash_sensitivity.py``: that file is copied
into the reference worktree for the v1.3.2 parity gate, and these tests
describe behaviour v1.3.2 does not have.
"""

import os
import re
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


class PatternRenderingTestCase(unittest.TestCase):
    """
    Harness for a task whose patterns contain templates.

    ``cmd`` is kept to a redirected ``echo`` so that it runs on every
    platform without naming an interpreter: what is under test is which
    files the *pattern* matches, not what the command does with them.
    """

    def setUp(self):
        self.runner = CliRunner()
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project_root = Path(self._tmp.name)
        self._original_cwd = os.getcwd()
        os.chdir(self.project_root)
        self.addCleanup(lambda: os.chdir(self._original_cwd))
        self.source_dir = self.project_root / "srcdir"
        self.source_dir.mkdir()
        self.source_file = self.source_dir / "a.txt"
        self.source_file.write_text("one\n")

    def write_recipe(self, text: str) -> None:
        (self.project_root / "tasktree.yaml").write_text(text)

    def run_task(self, task: str = "build", env: dict | None = None):
        result = self.runner.invoke(app, [task], env={"NO_COLOR": "1", **(env or {})})
        return result, strip_ansi_codes(result.stdout)

    def assert_ran(self, output: str, result, task: str = "build") -> None:
        self.assertEqual(result.exit_code, 0, output)
        self.assertIn(f"Running: {task}", output)

    def assert_skipped(self, output: str, result, task: str = "build") -> None:
        self.assertEqual(result.exit_code, 0, output)
        self.assertNotIn(f"Running: {task}", output)

    def touch_source(self) -> None:
        """Change a matched input, the one thing that should force a re-run."""
        time.sleep(0.01)
        self.source_file.write_text("two\n")

    def assert_tracks_its_inputs(self) -> None:
        """
        The whole contract in one sequence: run, settle, change an input,
        run again. A pattern that matched nothing passes the first two
        steps and fails the third.
        """
        result, output = self.run_task()
        self.assert_ran(output, result)

        result, output = self.run_task()
        self.assert_skipped(output, result)

        self.touch_source()
        result, output = self.run_task()
        self.assert_ran(output, result)


class TestFiltersInInputPatterns(PatternRenderingTestCase):
    """
    A filter is the cheapest thing the old regex pass could not express:
    ``PLACEHOLDER_PATTERN`` matches ``{{ var.name }}`` and nothing with a
    space and a pipe in it, so ``{{ var.dir | lower }}`` was never
    substituted and reached the glob verbatim.
    """

    def test_filter_in_anonymous_input_pattern_is_rendered(self):
        self.write_recipe(
            "variables:\n  dir: SRCDIR\n"
            "tasks:\n  build:\n"
            '    inputs: ["{{ var.dir | lower }}/*.txt"]\n'
            "    outputs: [out.txt]\n"
            "    cmd: echo done > out.txt\n"
        )
        self.assert_tracks_its_inputs()

    def test_filter_in_named_input_pattern_is_rendered(self):
        """Named inputs are a dict branch in every consumer; cover it too."""
        self.write_recipe(
            "variables:\n  dir: SRCDIR\n"
            "tasks:\n  build:\n"
            "    inputs:\n"
            '      - sources: "{{ var.dir | lower }}/*.txt"\n'
            "    outputs: [out.txt]\n"
            "    cmd: echo done > out.txt\n"
        )
        self.assert_tracks_its_inputs()


class TestFiltersInOutputPatterns(PatternRenderingTestCase):
    """
    Outputs fail the other way round. A pattern that never matches reports
    its outputs missing on every run, so the task re-runs for ever instead
    of going quiet -- noisy rather than silent, but just as wrong.
    """

    def assert_settles(self) -> None:
        """
        Run twice. The second run has nothing to do, and says so; a task
        whose output pattern matched nothing claims its outputs are missing
        and runs again.
        """
        result, output = self.run_task()
        self.assert_ran(output, result)

        result, output = self.run_task()
        self.assert_skipped(output, result)

    def test_filter_in_anonymous_output_pattern_is_rendered(self):
        self.write_recipe(
            "variables:\n  out: OUT.TXT\n"
            "tasks:\n  build:\n"
            "    inputs: [srcdir/a.txt]\n"
            '    outputs: ["{{ var.out | lower }}"]\n'
            "    cmd: echo done > out.txt\n"
        )
        self.assert_settles()

    def test_filter_in_named_output_pattern_is_rendered(self):
        self.write_recipe(
            "variables:\n  out: OUT.TXT\n"
            "tasks:\n  build:\n"
            "    inputs: [srcdir/a.txt]\n"
            "    outputs:\n"
            '      - result: "{{ var.out | lower }}"\n'
            "    cmd: echo done > out.txt\n"
        )
        self.assert_settles()

    def test_argument_in_output_pattern_is_rendered(self):
        """
        Arguments are the namespace a pattern renderer must get from the
        invocation rather than the recipe, so cover one explicitly.
        """
        self.write_recipe(
            "tasks:\n  build:\n"
            "    args:\n      - name: { default: out }\n"
            "    inputs: [srcdir/a.txt]\n"
            '    outputs: ["{{ arg.name }}.txt"]\n'
            "    cmd: echo done > {{ arg.name }}.txt\n"
        )
        self.assert_settles()


class TestInheritedDependencyPatterns(PatternRenderingTestCase):
    """
    A task inherits its dependencies' patterns -- their outputs, or their
    inputs when they declare no outputs -- and those are matched against
    the filesystem too, so they need rendering for the same reason the
    task's own patterns do. They render against the *dependency's*
    invocation, not the dependent's.
    """

    def test_inherits_a_dependencys_rendered_input_pattern(self):
        """
        A dependency with no outputs passes its inputs up. Unrendered, the
        dependent inherits a pattern matching nothing and goes quiet.
        """
        self.write_recipe(
            "variables:\n  dir: SRCDIR\n"
            "tasks:\n"
            "  generate:\n"
            '    inputs: ["{{ var.dir | lower }}/*.txt"]\n'
            "    cmd: echo generated\n"
            "  build:\n"
            "    deps: [generate]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo done > out.txt\n"
        )
        self.assert_tracks_its_inputs()

    def test_inherits_a_dependencys_rendered_output_pattern(self):
        """
        The commoner case: a dependency's outputs become the dependent's
        inputs, so a template in the producer's output path has to render
        before the consumer can notice it changing.
        """
        self.write_recipe(
            "variables:\n  built: BUILT.TXT\n"
            "tasks:\n"
            "  generate:\n"
            "    inputs: [srcdir/a.txt]\n"
            '    outputs: ["{{ var.built | lower }}"]\n'
            "    cmd: echo generated > built.txt\n"
            "  build:\n"
            "    deps: [generate]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo done > out.txt\n"
        )
        self.assert_tracks_its_inputs()


if __name__ == "__main__":
    unittest.main()
