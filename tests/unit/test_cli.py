"""Tests for CLI argument parsing."""

import unittest
from unittest.mock import patch

import click
import typer

from tasktree.cli_commands import (
    _supports_unicode,
    get_action_failure_string,
    get_action_success_string,
)
from tasktree.parser import parse_task_args
from tasktree.logging import LogLevel
from helpers.logging import logger_stub


class TestParseTaskArgs(unittest.TestCase):
    """
    Tests for _parse_task_args() function.
    """

    def test_parse_task_args_positional(self):
        """
        Test parsing positional arguments.
        """

        arg_specs = ["environment", "region"]
        arg_values = ["production", "us-east-1"]

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-east-1"})

    def test_parse_task_args_named(self):
        """
        Test parsing name=value arguments.
        """

        arg_specs = ["environment", "region"]
        arg_values = ["environment=production", "region=us-east-1"]

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-east-1"})

    def test_parse_task_args_with_defaults(self):
        """
        Test default values applied.
        """

        arg_specs = ["environment", {"region": {"default": "us-west-1"}}]
        arg_values = ["production"]  # Only provide first arg

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-west-1"})

    def test_parse_task_args_type_conversion(self):
        """
        Test values converted to correct types.
        """

        arg_specs = [
            {"port": {"type": "int"}},
            {"debug": {"type": "bool"}},
            {"timeout": {"type": "float"}},
        ]
        arg_values = ["8080", "true", "30.5"]

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"port": 8080, "debug": True, "timeout": 30.5})
        self.assertIsInstance(result["port"], int)
        self.assertIsInstance(result["debug"], bool)
        self.assertIsInstance(result["timeout"], float)

    def test_parse_task_args_unknown_argument(self):
        """
        Test error for unknown argument name.
        """

        arg_specs = ["environment"]
        arg_values = ["unknown_arg=value"]

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_too_many(self):
        """
        Test error for too many positional args.
        """

        arg_specs = ["environment"]
        arg_values = ["production", "extra_value"]

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_missing_required(self):
        """
        Test error for missing required argument.
        """

        arg_specs = ["environment", "region"]
        arg_values = ["production"]  # Missing 'region'

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_invalid_type(self):
        """
        Test error for invalid type conversion.
        """

        arg_specs = [{"port": {"type": "int"}}]
        arg_values = ["not_a_number"]

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_empty(self):
        """
        Test returns empty dict when no args.
        """

        arg_specs = []
        arg_values = []

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {})

    def test_parse_task_args_mixed(self):
        """
        Test mixing positional and named arguments.
        """

        arg_specs = ["environment", "region", {"verbose": {"type": "bool"}}]
        arg_values = ["production", "region=us-east-1", "verbose=true"]

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(
            result,
            {"environment": "production", "region": "us-east-1", "verbose": True},
        )


class TestLogLevelParsing(unittest.TestCase):
    """
    Tests for log level parsing logic.
    """

    def test_log_level_choice_accepts_valid_lowercase(self):
        """
        Test that Click.Choice accepts valid lowercase log levels.
        """
        choice = click.Choice(
            ["fatal", "error", "warn", "info", "debug", "trace"], case_sensitive=False
        )

        # All valid lowercase levels should be accepted
        for level in ["fatal", "error", "warn", "info", "debug", "trace"]:
            result = choice.convert(level, None, None)
            self.assertEqual(result, level)

    def test_log_level_choice_accepts_valid_uppercase(self):
        """
        Test that Click.Choice accepts valid uppercase log levels (case-insensitive).
        """
        choice = click.Choice(
            ["fatal", "error", "warn", "info", "debug", "trace"], case_sensitive=False
        )

        # All uppercase variants should be normalized to lowercase
        test_cases = [
            ("FATAL", "fatal"),
            ("ERROR", "error"),
            ("WARN", "warn"),
            ("INFO", "info"),
            ("DEBUG", "debug"),
            ("TRACE", "trace"),
        ]

        for input_val, expected in test_cases:
            result = choice.convert(input_val, None, None)
            self.assertEqual(result, expected)

    def test_log_level_choice_accepts_mixed_case(self):
        """
        Test that Click.Choice accepts mixed case log levels.
        """
        choice = click.Choice(
            ["fatal", "error", "warn", "info", "debug", "trace"], case_sensitive=False
        )

        # Mixed case variants should be normalized to lowercase
        test_cases = [
            ("Info", "info"),
            ("DeBuG", "debug"),
            ("WaRn", "warn"),
        ]

        for input_val, expected in test_cases:
            result = choice.convert(input_val, None, None)
            self.assertEqual(result, expected)

    def test_log_level_choice_rejects_invalid(self):
        """
        Test that Click.Choice raises BadParameter for invalid log levels.
        """
        choice = click.Choice(
            ["fatal", "error", "warn", "info", "debug", "trace"], case_sensitive=False
        )

        # Invalid values should raise click.BadParameter
        invalid_levels = ["verbose", "123", "warning", "critical", ""]

        for invalid in invalid_levels:
            with self.assertRaises(click.BadParameter) as cm:
                choice.convert(invalid, None, None)
            # Error message should indicate invalid choice
            self.assertIn("is not one of", str(cm.exception).lower())

    def test_log_level_mapping_to_enum(self):
        """
        Test that log level strings map to correct LogLevel enum values.
        """
        log_level_map = {
            "fatal": LogLevel.FATAL,
            "error": LogLevel.ERROR,
            "warn": LogLevel.WARN,
            "info": LogLevel.INFO,
            "debug": LogLevel.DEBUG,
            "trace": LogLevel.TRACE,
        }

        # Verify all mappings are correct
        self.assertEqual(log_level_map["fatal"], LogLevel.FATAL)
        self.assertEqual(log_level_map["error"], LogLevel.ERROR)
        self.assertEqual(log_level_map["warn"], LogLevel.WARN)
        self.assertEqual(log_level_map["info"], LogLevel.INFO)
        self.assertEqual(log_level_map["debug"], LogLevel.DEBUG)
        self.assertEqual(log_level_map["trace"], LogLevel.TRACE)


class TestUnicodeSupport(unittest.TestCase):
    """
    Tests for Unicode symbol detection functions.
    """

    @patch("tasktree.cli_commands.os.environ", {})
    @patch("tasktree.cli_commands.os.name", "posix")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_with_utf8_encoding(self, mock_stdout):
        """
        Test that UTF-8 encoding returns True.
        """
        mock_stdout.encoding = "utf-8"
        self.assertTrue(_supports_unicode())

    @patch("tasktree.cli_commands.os.environ", {})
    @patch("tasktree.cli_commands.os.name", "posix")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_with_utf8_uppercase(self, mock_stdout):
        """
        Test that UTF-8 (uppercase) encoding returns True.
        """
        mock_stdout.encoding = "UTF-8"
        self.assertTrue(_supports_unicode())

    @patch("tasktree.cli_commands.os.environ", {})
    @patch("tasktree.cli_commands.os.name", "nt")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_on_classic_windows_console(self, mock_stdout):
        """
        Test that classic Windows console (conhost) returns False.
        """
        mock_stdout.encoding = "utf-8"
        # No WT_SESSION in environ means classic console
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli_commands.os.environ", {"WT_SESSION": "some-value"})
    @patch("tasktree.cli_commands.os.name", "nt")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_on_windows_terminal(self, mock_stdout):
        """
        Test that Windows Terminal with UTF-8 returns True.
        """
        mock_stdout.encoding = "utf-8"
        # WT_SESSION present means Windows Terminal
        self.assertTrue(_supports_unicode())

    @patch("tasktree.cli_commands.os.environ", {})
    @patch("tasktree.cli_commands.os.name", "posix")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_with_encoding_that_fails_encode(self, mock_stdout):
        """
        Test that encoding that can't encode symbols returns False.
        """
        # ASCII encoding will fail to encode ✓✗
        mock_stdout.encoding = "ascii"
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli_commands.os.environ", {})
    @patch("tasktree.cli_commands.os.name", "posix")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_with_none_encoding(self, mock_stdout):
        """
        Test that None encoding returns False.
        """
        mock_stdout.encoding = None
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli_commands.os.environ", {})
    @patch("tasktree.cli_commands.os.name", "posix")
    @patch("tasktree.cli_commands.sys.stdout")
    def test_supports_unicode_with_latin1_encoding(self, mock_stdout):
        """
        Test that Latin-1 encoding returns False (can't encode symbols).
        """
        mock_stdout.encoding = "latin-1"
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli_commands._supports_unicode")
    def test_get_action_success_string_with_unicode(self, mock_supports):
        """
        Test success string returns Unicode symbol when supported.
        """
        mock_supports.return_value = True
        self.assertEqual(get_action_success_string(), "✓")

    @patch("tasktree.cli_commands._supports_unicode")
    def test_get_action_success_string_without_unicode(self, mock_supports):
        """
        Test success string returns ASCII when Unicode not supported.
        """
        mock_supports.return_value = False
        self.assertEqual(get_action_success_string(), "[ OK ]")

    @patch("tasktree.cli_commands._supports_unicode")
    def test_get_action_failure_string_with_unicode(self, mock_supports):
        """
        Test failure string returns Unicode symbol when supported.
        """
        mock_supports.return_value = True
        self.assertEqual(get_action_failure_string(), "✗")

    @patch("tasktree.cli_commands._supports_unicode")
    def test_get_action_failure_string_without_unicode(self, mock_supports):
        """
        Test failure string returns ASCII when Unicode not supported.
        """
        mock_supports.return_value = False
        self.assertEqual(get_action_failure_string(), "[ FAIL ]")


class TestTaskOutputParameter(unittest.TestCase):
    """
    Test task_output CLI parameter handling.
    """

    def test_task_output_accepts_all(self):
        """
        Test that task_output parameter accepts "all" value.
        """
        # This is a simple smoke test verifying Click accepts the value
        # The actual normalization is handled by Click's Choice type
        choice = click.Choice(["all"], case_sensitive=False)

        # Should accept lowercase
        result = choice.convert("all", None, None)
        self.assertEqual(result, "all")

        # Should accept uppercase (case-insensitive)
        result = choice.convert("ALL", None, None)
        self.assertEqual(result, "all")


if __name__ == "__main__":
    unittest.main()
