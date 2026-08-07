"""
Tests for turning jsonschema's validation errors into messages a recipe
author can act on.
"""

import json
import unittest
from pathlib import Path

import jsonschema

from tasktree.recipe_schema import merged_tree_schema, schema_error_message

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "tasktree-schema.json"
RECIPE_PATH = Path("/projects/demo/tasktree.yaml")


def _message(tree: dict) -> str:
    schema = merged_tree_schema(json.loads(SCHEMA_PATH.read_text()))
    validator = jsonschema.Draft7Validator(schema)
    error = jsonschema.exceptions.best_match(validator.iter_errors(tree))
    assert error is not None, "expected the tree to be invalid"
    return schema_error_message(error, RECIPE_PATH)


class TestRemediationHints(unittest.TestCase):
    """
    Where a hand-written check used to teach the fix, the schema message
    alone would be a step backwards, so the formatter carries the hint.
    """

    def test_args_as_a_mapping_says_how_to_write_a_list(self):
        message = _message(
            {"tasks": {"build": {"cmd": "make", "args": {"x": {"type": "int"}}}}}
        )
        self.assertIn("tasks.build.args", message)
        self.assertIn("- x:", message)

    def test_hint_is_specific_to_the_field(self):
        """A wrong type elsewhere gets no args advice."""
        message = _message({"tasks": {"build": {"cmd": "make", "inputs": 42}}})
        self.assertNotIn("- x:", message)


class TestErrorMessages(unittest.TestCase):
    """
    Every message names the file, points at the offending location in
    recipe terms, and says what is wrong without quoting schema internals.
    """

    def test_names_the_recipe_file(self):
        self.assertIn(str(RECIPE_PATH), _message({"tasks": {"build": {}}}))

    def test_missing_cmd_points_at_the_task(self):
        message = _message({"tasks": {"build": {"desc": "no command"}}})
        self.assertIn("tasks.build", message)
        self.assertIn("cmd", message)

    def test_unknown_field_points_at_the_field(self):
        message = _message({"tasks": {"build": {"cmd": "make", "outpts": ["a"]}}})
        self.assertIn("tasks.build", message)
        self.assertIn("outpts", message)

    def test_wrong_type_says_what_was_expected(self):
        message = _message({"tasks": {"build": {"cmd": ["make", "install"]}}})
        self.assertIn("tasks.build.cmd", message)
        self.assertIn("string", message)

    def test_indexes_into_lists(self):
        message = _message({"tasks": {"build": {"cmd": "make", "inputs": [{"a": 1}]}}})
        self.assertIn("tasks.build.inputs[0]", message)

    def test_names_a_dotted_task_without_ambiguity(self):
        message = _message({"tasks": {"build.release": {}}})
        self.assertIn("tasks['build.release']", message)

    def test_alternatives_list_the_forms_that_are_accepted(self):
        """
        The rejected value's own schema describes the *name* key, not the
        value, so the branch descriptions are what the author needs.
        """
        message = _message({"variables": {"where": ["a", "b"]}})
        self.assertIn("Simple string value", message)
        self.assertIn("Environment variable reference", message)
        self.assertNotIn("dots not allowed", message)

    def test_field_on_the_wrong_runner_kind_says_so(self):
        message = _message({"runners": {"r": {"dockerfile": "Dockerfile"}}})
        self.assertIn("runners.r", message)
        self.assertIn("dockerfile", message)
        self.assertIn("type", message)
        self.assertNotIn("should not be valid under", message)

    def test_alternatives_are_explained_not_dumped(self):
        """A oneOf failure must not spill the branch schemas at the user."""
        message = _message({"variables": {"where": ["a", "b"]}})
        self.assertIn("variables.where", message)
        self.assertNotIn("additionalProperties", message)
        self.assertNotIn("{'type'", message)

    def test_message_stays_short(self):
        message = _message({"variables": {"where": ["a", "b"]}})
        self.assertLess(len(message.splitlines()), 6)


if __name__ == "__main__":
    unittest.main()
