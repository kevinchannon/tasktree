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


class TestNothingIsRenderedTwice(PatternRenderingTestCase):
    """
    A path is data by the time it reaches a command: whatever a variable
    evaluated to has to arrive literally, even when it happens to look
    like a template.

    Slice 10b achieved this for the *injection* step -- a path now reaches
    the command through the render context rather than being substituted
    into the command text beforehand, which is covered at unit level by
    ``TestSelfNamespaceRendering`` in ``tests/unit/test_executor.py``.
    End to end it is still wrong, and for a different reason: the
    parse-time substitution pass writes variable *values* into the pattern
    text, and slice 10a renders patterns, so the value is rendered on its
    way through. Only deleting that pass (slice 10d) closes it.

    Kept as a running gate rather than a note in the plan: it fails for the
    exact reason 10d exists, and an unexpected pass means 10d has landed
    and the marker should come off.
    """

    @unittest.expectedFailure
    def test_a_variable_value_containing_a_template_stays_literal(self):
        """
        The value arrives from the environment, so it is data and never a
        template: a recipe-literal spelling would be rendered once on its
        way in and prove nothing.
        """
        self.write_recipe(
            "variables:\n"
            "  braced: { env: TT_BRACED }\n"
            "tasks:\n  build:\n"
            "    inputs:\n"
            '      - src: "{{ var.braced }}"\n'
            "    outputs: [out.txt]\n"
            "    cmd: echo {{ self.inputs.src }} > out.txt\n"
        )
        result, output = self.run_task(env={"TT_BRACED": "{{ oops }}"})
        self.assert_ran(output, result)
        self.assertEqual(
            (self.project_root / "out.txt").read_text().strip(), "{{ oops }}"
        )


class TestTemplatesInArgumentSpecs(PatternRenderingTestCase):
    """
    An argument's default, bounds and choices are read and converted to the
    argument's declared type while the CLI is still assembling arguments,
    before any task renders -- so they cannot wait for the renderer the way
    a command does (schema pipeline slice 10c).

    They are invocation-independent, though: an argument default cannot
    name an argument. So unlike a pattern, one render up front is the right
    shape for them, and the old regex pass was in the right place -- just
    unable to express anything but a bare {{ var.name }}.
    """

    def test_a_filter_in_an_argument_default_is_rendered(self):
        self.write_recipe(
            "variables:\n  tag: RELEASE\n"
            "tasks:\n  build:\n"
            "    args:\n"
            '      - name: { default: "{{ var.tag | lower }}" }\n'
            "    inputs: [srcdir/a.txt]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo {{ arg.name }} > out.txt\n"
        )
        result, output = self.run_task()
        self.assert_ran(output, result)
        self.assertEqual((self.project_root / "out.txt").read_text().strip(), "release")

    @unittest.expectedFailure
    def test_a_filter_in_a_choice_is_rendered(self):
        """
        Choices constrain the value, so an unrendered one rejects the very
        default it was meant to allow.

        Still failing, and not for a rendering reason: ``_parse_arg_dict``
        validates default-against-choices while the *recipe* is parsed,
        which is before variables are evaluated, so the check compares a
        rendered default with unrendered choices and rejects the recipe
        before anything can run. A template in a choice has therefore never
        worked. Making it work means deferring that validation to the point
        of use, which belongs with the validation pipeline rather than with
        moving a renderer; kept as a running gate so it reports itself when
        that lands.
        """
        self.write_recipe(
            "variables:\n  tag: RELEASE\n"
            "tasks:\n  build:\n"
            "    args:\n"
            "      - name:\n"
            "          default: release\n"
            '          choices: ["{{ var.tag | lower }}", debug]\n'
            "    inputs: [srcdir/a.txt]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo {{ arg.name }} > out.txt\n"
        )
        result, output = self.run_task()
        self.assert_ran(output, result)
        self.assertEqual((self.project_root / "out.txt").read_text().strip(), "release")


class TestBuiltinsInArgumentSpecs(PatternRenderingTestCase):
    """
    The tt.* values that describe the host and the project need neither a
    task nor a run, so an argument default may name them. The ones that do
    depend on the run are reported rather than handed to the shell as text,
    which is what used to happen.
    """

    def test_a_host_builtin_in_a_default_reaches_the_command(self):
        self.write_recipe(
            "tasks:\n  build:\n"
            "    args:\n"
            '      - where: { default: "{{ tt.project_root }}" }\n'
            "    inputs: [srcdir/a.txt]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo {{ arg.where }} > out.txt\n"
        )
        result, output = self.run_task()
        self.assert_ran(output, result)
        self.assertEqual(
            (self.project_root / "out.txt").read_text().strip(),
            str(self.project_root.resolve()),
        )

    def test_the_task_name_in_a_description_reaches_the_listing(self):
        self.write_recipe(
            "tasks:\n  build:\n"
            '    desc: "Runs {{ tt.task_name }}"\n'
            "    inputs: [srcdir/a.txt]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo done > out.txt\n"
        )
        result = self.runner.invoke(app, ["--list"], env={"NO_COLOR": "1"})
        output = strip_ansi_codes(result.stdout)

        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("Runs build", output)

    def test_a_builtin_that_needs_a_run_is_refused(self):
        self.write_recipe(
            "tasks:\n  build:\n"
            "    args:\n"
            '      - where: { default: "{{ tt.working_dir }}" }\n'
            "    inputs: [srcdir/a.txt]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo {{ arg.where }} > out.txt\n"
        )
        result, output = self.run_task()

        self.assertNotEqual(result.exit_code, 0, output)
        self.assertIn("tt.working_dir", " ".join(output.split()))


class TestTemplatesInDescriptions(PatternRenderingTestCase):
    """
    A description is printed by --list, where there is no invocation at
    all, so it is the other clear case for rendering early and once rather
    than at the point of use.
    """

    def test_a_filter_in_a_description_is_rendered(self):
        self.write_recipe(
            "variables:\n  product: TaskTree\n"
            "tasks:\n  build:\n"
            '    desc: "Builds {{ var.product | upper }}"\n'
            "    inputs: [srcdir/a.txt]\n"
            "    outputs: [out.txt]\n"
            "    cmd: echo done > out.txt\n"
        )
        result = self.runner.invoke(app, ["--list"], env={"NO_COLOR": "1"})
        output = strip_ansi_codes(result.stdout)

        self.assertEqual(result.exit_code, 0, output)
        self.assertIn("Builds TASKTREE", output)


if __name__ == "__main__":
    unittest.main()
