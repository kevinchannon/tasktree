"""Tests for CLI argument parsing."""

import unittest
from unittest.mock import patch

import typer

from tasktree.cli import _parse_task_args


class TestParseTaskArgs(unittest.TestCase):
    """Tests for _parse_task_args() function."""

    def test_parse_task_args_positional(self):
        """Test parsing positional arguments."""
        arg_specs = ["environment", "region"]
        arg_values = ["production", "us-east-1"]

        result = _parse_task_args(arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-east-1"})

    def test_parse_task_args_named(self):
        """Test parsing name=value arguments."""
        arg_specs = ["environment", "region"]
        arg_values = ["environment=production", "region=us-east-1"]

        result = _parse_task_args(arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-east-1"})

    def test_parse_task_args_with_defaults(self):
        """Test default values applied."""
        arg_specs = ["environment", {"region": {"default": "us-west-1"}}]
        arg_values = ["production"]  # Only provide first arg

        result = _parse_task_args(arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-west-1"})

    def test_parse_task_args_type_conversion(self):
        """Test values converted to correct types."""
        arg_specs = [{"port": {"type": "int"}}, {"debug": {"type": "bool"}}, {"timeout": {"type": "float"}}]
        arg_values = ["8080", "true", "30.5"]

        result = _parse_task_args(arg_specs, arg_values)

        self.assertEqual(result, {"port": 8080, "debug": True, "timeout": 30.5})
        self.assertIsInstance(result["port"], int)
        self.assertIsInstance(result["debug"], bool)
        self.assertIsInstance(result["timeout"], float)

    def test_parse_task_args_unknown_argument(self):
        """Test error for unknown argument name."""
        arg_specs = ["environment"]
        arg_values = ["unknown_arg=value"]

        with self.assertRaises(typer.Exit):
            _parse_task_args(arg_specs, arg_values)

    def test_parse_task_args_too_many(self):
        """Test error for too many positional args."""
        arg_specs = ["environment"]
        arg_values = ["production", "extra_value"]

        with self.assertRaises(typer.Exit):
            _parse_task_args(arg_specs, arg_values)

    def test_parse_task_args_missing_required(self):
        """Test error for missing required argument."""
        arg_specs = ["environment", "region"]
        arg_values = ["production"]  # Missing 'region'

        with self.assertRaises(typer.Exit):
            _parse_task_args(arg_specs, arg_values)

    def test_parse_task_args_invalid_type(self):
        """Test error for invalid type conversion."""
        arg_specs = [{"port": {"type": "int"}}]
        arg_values = ["not_a_number"]

        with self.assertRaises(typer.Exit):
            _parse_task_args(arg_specs, arg_values)

    def test_parse_task_args_empty(self):
        """Test returns empty dict when no args."""
        arg_specs = []
        arg_values = []

        result = _parse_task_args(arg_specs, arg_values)

        self.assertEqual(result, {})

    def test_parse_task_args_mixed(self):
        """Test mixing positional and named arguments."""
        arg_specs = ["environment", "region", {"verbose": {"type": "bool"}}]
        arg_values = ["production", "region=us-east-1", "verbose=true"]

        result = _parse_task_args(arg_specs, arg_values)

        self.assertEqual(result, {
            "environment": "production",
            "region": "us-east-1",
            "verbose": True
        })


if __name__ == "__main__":
    unittest.main()
