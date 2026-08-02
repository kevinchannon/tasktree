"""
Tests validating recipe snippets against schema/tasktree-schema.json.
"""

import json
import unittest
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "tasktree-schema.json"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"

# Fixtures the schema is *meant* to reject, with the reason. Everything else
# under tests/fixtures must validate: the schema may never be stricter than
# the recipes tt actually runs.
INTENTIONALLY_INVALID = {
    "e2e_task_name_with_dot/tasktree.yaml": "dotted task names are reserved for namespacing",
}


def _validate(recipe: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.validate(instance=recipe, schema=schema)


def _runner_recipe(runner: dict) -> dict:
    return {"runners": {"my-runner": runner}}


class TestRunnerSchema(unittest.TestCase):
    """
    Tests for the runnerDef schema: host, docker and nix runner shapes.
    """

    def test_host_runner_valid(self):
        _validate(_runner_recipe({"interpreter": "bash"}))

    def test_docker_runner_valid(self):
        _validate(
            _runner_recipe(
                {
                    "type": "containerised",
                    "engine": "docker",
                    "dockerfile": "Dockerfile",
                    "context": ".",
                }
            )
        )

    def test_docker_field_without_type_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(_runner_recipe({"dockerfile": "Dockerfile"}))

    def test_nix_runner_valid(self):
        _validate(_runner_recipe({"type": "nix", "flake": "."}))

    def test_nix_runner_with_devshell_valid(self):
        _validate(_runner_recipe({"type": "nix", "flake": "./sub", "devshell": "ci"}))

    def test_nix_runner_without_flake_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(_runner_recipe({"type": "nix"}))

    def test_flake_without_type_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(_runner_recipe({"flake": "."}))

    def test_devshell_without_type_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(_runner_recipe({"devshell": "ci"}))

    def test_container_field_on_nix_runner_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(
                _runner_recipe(
                    {"type": "nix", "flake": ".", "dockerfile": "Dockerfile"}
                )
            )

    def test_flake_on_containerised_runner_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(
                _runner_recipe(
                    {
                        "type": "containerised",
                        "engine": "docker",
                        "dockerfile": "Dockerfile",
                        "flake": ".",
                    }
                )
            )

    def test_unknown_type_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate(_runner_recipe({"type": "virtualised"}))


class TestVariableSchema(unittest.TestCase):
    """
    Tests for the variables section: the scalar forms tt accepts as a
    variable's value, and the env/read/eval reference forms.
    """

    def test_string_value_valid(self):
        _validate({"variables": {"greeting": "hello"}})

    def test_integer_value_valid(self):
        _validate({"variables": {"port": 8080}})

    def test_float_value_valid(self):
        _validate({"variables": {"ratio": 1.5}})

    def test_boolean_value_valid(self):
        _validate({"variables": {"enabled": True}})

    def test_env_reference_valid(self):
        _validate({"variables": {"home": {"env": "HOME", "default": "/root"}}})

    def test_list_value_invalid(self):
        with self.assertRaises(jsonschema.ValidationError):
            _validate({"variables": {"parts": ["a", "b"]}})


def _recipe_fixtures() -> dict[str, dict]:
    """
    Every parseable recipe under tests/fixtures, keyed by its path relative to
    the fixture root.
    """
    recipes = {}
    for path in sorted(FIXTURE_ROOT.rglob("*")):
        if path.suffix not in {".yaml", ".yml", ".tasks"} or not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue  # fixtures for tt's own YAML-error handling
        if isinstance(data, dict):
            recipes[str(path.relative_to(FIXTURE_ROOT))] = data
    return recipes


class TestFixtureCorpus(unittest.TestCase):
    """
    The whole fixture corpus validated against the schema. This is the net
    that catches the schema drifting stricter than the parser: every recipe
    here is one tt is expected to handle.
    """

    def test_every_fixture_recipe_validates(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        validator = jsonschema.Draft7Validator(schema)

        rejected = {}
        for name, recipe in _recipe_fixtures().items():
            error = jsonschema.exceptions.best_match(validator.iter_errors(recipe))
            if error is not None:
                rejected[name] = error.message

        self.assertEqual(
            sorted(rejected),
            sorted(INTENTIONALLY_INVALID),
            f"unexpected schema rejections: {rejected}",
        )

    def test_corpus_is_not_empty(self):
        self.assertGreater(len(_recipe_fixtures()), 100)


if __name__ == "__main__":
    unittest.main()
