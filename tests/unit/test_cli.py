"""Tests for CLI argument parsing."""

import sys
import unittest
from unittest.mock import MagicMock, patch

import typer

from tasktree.cli import (
    _parse_task_args,
    _supports_unicode,
    get_action_failure_string,
    get_action_success_string,
)


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


class TestUnicodeSupport(unittest.TestCase):
    """Tests for Unicode symbol detection functions."""

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_with_utf8_encoding(self, mock_platform, mock_stdout):
        """Test that UTF-8 encoding returns True."""
        mock_stdout.encoding = 'utf-8'
        self.assertTrue(_supports_unicode())

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_with_utf8_uppercase(self, mock_platform, mock_stdout):
        """Test that UTF-8 (uppercase) encoding returns True."""
        mock_stdout.encoding = 'UTF-8'
        self.assertTrue(_supports_unicode())

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_on_windows_without_utf8(self, mock_platform, mock_stdout):
        """Test that Windows without UTF-8 encoding returns False."""
        mock_stdout.encoding = 'cp1252'
        mock_platform.return_value = 'Windows'
        self.assertFalse(_supports_unicode())

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_on_non_windows_without_utf8(self, mock_platform, mock_stdout):
        """Test that non-Windows without UTF-8 encoding returns False for safety."""
        mock_stdout.encoding = 'latin-1'
        mock_platform.return_value = 'Linux'
        self.assertFalse(_supports_unicode())

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_with_none_encoding_on_windows(self, mock_platform, mock_stdout):
        """Test that None encoding on Windows returns False."""
        mock_stdout.encoding = None
        mock_platform.return_value = 'Windows'
        self.assertFalse(_supports_unicode())

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_with_none_encoding_on_linux(self, mock_platform, mock_stdout):
        """Test that None encoding on Linux returns False for safety."""
        mock_stdout.encoding = None
        mock_platform.return_value = 'Linux'
        self.assertFalse(_supports_unicode())

    @patch('tasktree.cli.sys.stdout')
    @patch('tasktree.cli.platform.system')
    def test_supports_unicode_without_encoding_attribute(self, mock_platform, mock_stdout):
        """Test handling of missing encoding attribute returns False for safety."""
        # Create a mock without encoding attribute
        mock_stdout_no_encoding = MagicMock(spec=[])
        with patch('tasktree.cli.sys.stdout', mock_stdout_no_encoding):
            mock_platform.return_value = 'Linux'
            self.assertFalse(_supports_unicode())

    @patch('tasktree.cli._supports_unicode')
    def test_get_action_success_string_with_unicode(self, mock_supports):
        """Test success string returns Unicode symbol when supported."""
        mock_supports.return_value = True
        self.assertEqual(get_action_success_string(), "✓")

    @patch('tasktree.cli._supports_unicode')
    def test_get_action_success_string_without_unicode(self, mock_supports):
        """Test success string returns ASCII when Unicode not supported."""
        mock_supports.return_value = False
        self.assertEqual(get_action_success_string(), "[ OK ]")

    @patch('tasktree.cli._supports_unicode')
    def test_get_action_failure_string_with_unicode(self, mock_supports):
        """Test failure string returns Unicode symbol when supported."""
        mock_supports.return_value = True
        self.assertEqual(get_action_failure_string(), "✗")

    @patch('tasktree.cli._supports_unicode')
    def test_get_action_failure_string_without_unicode(self, mock_supports):
        """Test failure string returns ASCII when Unicode not supported."""
        mock_supports.return_value = False
        self.assertEqual(get_action_failure_string(), "[ FAIL ]")


if __name__ == "__main__":
    unittest.main()
