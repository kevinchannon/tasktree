"""
Integration tests for schema validation of recipes at parse time.

Self-contained on purpose (only parse_recipe is imported) so the file can be
copied into the v1.3.2 reference worktree for the parity gate.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.parser import parse_recipe


class SchemaValidationTestCase(unittest.TestCase):
    def parse(self, recipe_text: str, **kwargs):
        with TemporaryDirectory() as tmpdir:
            recipe_path = Path(tmpdir) / "tasktree.yaml"
            recipe_path.write_text(recipe_text)
            return parse_recipe(recipe_path, **kwargs)


class TestStructuralMistakesAreCaught(SchemaValidationTestCase):
    """
    Mistakes no hand-written check looks for. Each of these parsed happily
    before, and went wrong later or not at all: a misspelled field is simply
    ignored, so the task quietly does the wrong thing.
    """

    def test_misspelled_task_field_rejected(self):
        with self.assertRaises(ValueError) as cm:
            self.parse("tasks:\n  build:\n    cmd: make\n    outpts: [bin]\n")
        self.assertIn("outpts", str(cm.exception))

    def test_misspelled_runner_field_rejected(self):
        with self.assertRaises(ValueError) as cm:
            self.parse(
                "runners:\n  sh:\n    shell: {cmd: bash}\n"
                "tasks:\n  build:\n    cmd: make\n    runner: sh\n"
            )
        self.assertIn("shell", str(cm.exception))

    def test_non_string_description_rejected(self):
        with self.assertRaises(ValueError):
            self.parse("tasks:\n  build:\n    cmd: make\n    desc: 42\n")

    def test_dependency_arguments_of_the_wrong_shape_rejected(self):
        """Args must be a list or a mapping; a bare string is neither."""
        with self.assertRaises(ValueError) as cm:
            self.parse(
                "tasks:\n"
                "  build:\n"
                "    cmd: make\n"
                "    deps:\n"
                "      - other: 'msg=hi'\n"
                "  other:\n"
                "    cmd: echo\n"
            )
        self.assertIn("deps", str(cm.exception))

    def test_valid_recipe_still_parses(self):
        recipe = self.parse(
            "variables:\n"
            "  port: 8080\n"
            "runners:\n"
            "  sh:\n"
            "    interpreter: {cmd: bash}\n"
            "tasks:\n"
            "  build:\n"
            "    desc: builds\n"
            "    cmd: make\n"
            "    runner: sh\n"
        )
        self.assertIn("build", recipe.tasks)


class TestErrorMessagesLocateTheProblem(SchemaValidationTestCase):
    """
    A schema error must read like a recipe error, not a schema dump.
    """

    def test_message_names_the_task_and_the_field(self):
        with self.assertRaises(ValueError) as cm:
            self.parse("tasks:\n  build:\n    cmd: make\n    outpts: [bin]\n")
        message = str(cm.exception)
        self.assertIn("tasks.build", message)
        self.assertIn("outpts", message)

    def test_graph_checks_keep_their_own_wording(self):
        """
        Only structural checks retire. Graph and lifecycle questions the
        schema cannot answer stay in Python, with their own messages.
        """
        with self.assertRaises(ValueError) as cm:
            self.parse(
                "tasks:\n  build:\n    cmd: make\n    runner: nope\n",
                root_task="build",
            )
        self.assertIn("nope", str(cm.exception))
        self.assertNotIn("is not of type", str(cm.exception))

    def test_message_does_not_dump_the_schema(self):
        with self.assertRaises(ValueError) as cm:
            self.parse("tasks:\n  build:\n    cmd: make\n    inputs: [{a: 1}]\n")
        message = str(cm.exception)
        self.assertNotIn("additionalProperties", message)
        self.assertLess(len(message.splitlines()), 6)


class TestValidationRespectsExistingTolerance(SchemaValidationTestCase):
    """
    Validation runs on the pruned tree and after the merge's own lazy name
    reporting, so neither tolerance is lost to it.
    """

    def test_broken_unreachable_task_is_still_tolerated(self):
        recipe = self.parse(
            "tasks:\n"
            "  wanted:\n"
            "    cmd: echo hi\n"
            "  broken:\n"
            "    cmd: echo bye\n"
            "    outpts: [typo]\n",
            root_task="wanted",
            prune_unreachable=True,
        )
        self.assertIn("wanted", recipe.tasks)

    def test_unreferenced_bad_name_is_still_reported_lazily(self):
        recipe = self.parse(
            'variables:\n  "": hello\n  good: world\n'
            "tasks:\n  build:\n    cmd: echo {{ var.good }}\n",
            root_task="build",
        )
        self.assertIn("", recipe._name_errors)


if __name__ == "__main__":
    unittest.main()
