"""
Tests validating recipe snippets against schema/tasktree-schema.json.
"""

import json
import unittest
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).parents[2] / "schema" / "tasktree-schema.json"


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


if __name__ == "__main__":
    unittest.main()
