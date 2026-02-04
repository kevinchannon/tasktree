"""Tests for CLI argument parsing."""

import unittest
from unittest.mock import patch

import click
import typer

from tasktree.cli import (
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
    @athena: cdf5392be1c1
    """

    def test_parse_task_args_positional(self):
        """
        Test parsing positional arguments.
        @athena: 86dee375f117
        """

        arg_specs = ["environment", "region"]
        arg_values = ["production", "us-east-1"]

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-east-1"})

    def test_parse_task_args_named(self):
        """
        Test parsing name=value arguments.
        @athena: 151666470d4b
        """

        arg_specs = ["environment", "region"]
        arg_values = ["environment=production", "region=us-east-1"]

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-east-1"})

    def test_parse_task_args_with_defaults(self):
        """
        Test default values applied.
        @athena: 598d132f55eb
        """

        arg_specs = ["environment", {"region": {"default": "us-west-1"}}]
        arg_values = ["production"]  # Only provide first arg

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {"environment": "production", "region": "us-west-1"})

    def test_parse_task_args_type_conversion(self):
        """
        Test values converted to correct types.
        @athena: 09d4e79fa590
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
        @athena: 58e0bca425cb
        """

        arg_specs = ["environment"]
        arg_values = ["unknown_arg=value"]

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_too_many(self):
        """
        Test error for too many positional args.
        @athena: 416bdeec6f1a
        """

        arg_specs = ["environment"]
        arg_values = ["production", "extra_value"]

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_missing_required(self):
        """
        Test error for missing required argument.
        @athena: e6321cd30788
        """

        arg_specs = ["environment", "region"]
        arg_values = ["production"]  # Missing 'region'

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_invalid_type(self):
        """
        Test error for invalid type conversion.
        @athena: 1f4ecdaeeae9
        """

        arg_specs = [{"port": {"type": "int"}}]
        arg_values = ["not_a_number"]

        with self.assertRaises(typer.Exit):
            parse_task_args(logger_stub, arg_specs, arg_values)

    def test_parse_task_args_empty(self):
        """
        Test returns empty dict when no args.
        @athena: 76b95d186510
        """

        arg_specs = []
        arg_values = []

        result = parse_task_args(logger_stub, arg_specs, arg_values)

        self.assertEqual(result, {})

    def test_parse_task_args_mixed(self):
        """
        Test mixing positional and named arguments.
        @athena: 52b4d983582d
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
    @athena: 40bc1a8e3c02
    """

    def test_log_level_choice_accepts_valid_lowercase(self):
        """
        Test that Click.Choice accepts valid lowercase log levels.
        @athena: 0b34cda291d1
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
        @athena: 17deb52ea4f0
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
        @athena: 7dcc37b7668e
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
        @athena: e364c6cf1d62
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
        @athena: 92e594492835
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
    @athena: 8f0158c7f379
    """

    @patch("tasktree.cli.os.environ", {})
    @patch("tasktree.cli.os.name", "posix")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_with_utf8_encoding(self, mock_stdout):
        """
        Test that UTF-8 encoding returns True.
        @athena: 7009d2f9ca86
        """
        mock_stdout.encoding = "utf-8"
        self.assertTrue(_supports_unicode())

    @patch("tasktree.cli.os.environ", {})
    @patch("tasktree.cli.os.name", "posix")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_with_utf8_uppercase(self, mock_stdout):
        """
        Test that UTF-8 (uppercase) encoding returns True.
        @athena: 4e46014bc2de
        """
        mock_stdout.encoding = "UTF-8"
        self.assertTrue(_supports_unicode())

    @patch("tasktree.cli.os.environ", {})
    @patch("tasktree.cli.os.name", "nt")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_on_classic_windows_console(self, mock_stdout):
        """
        Test that classic Windows console (conhost) returns False.
        @athena: e96c0a119f81
        """
        mock_stdout.encoding = "utf-8"
        # No WT_SESSION in environ means classic console
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli.os.environ", {"WT_SESSION": "some-value"})
    @patch("tasktree.cli.os.name", "nt")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_on_windows_terminal(self, mock_stdout):
        """
        Test that Windows Terminal with UTF-8 returns True.
        @athena: 33983df2ba93
        """
        mock_stdout.encoding = "utf-8"
        # WT_SESSION present means Windows Terminal
        self.assertTrue(_supports_unicode())

    @patch("tasktree.cli.os.environ", {})
    @patch("tasktree.cli.os.name", "posix")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_with_encoding_that_fails_encode(self, mock_stdout):
        """
        Test that encoding that can't encode symbols returns False.
        @athena: 1cc3c46bb99b
        """
        # ASCII encoding will fail to encode ✓✗
        mock_stdout.encoding = "ascii"
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli.os.environ", {})
    @patch("tasktree.cli.os.name", "posix")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_with_none_encoding(self, mock_stdout):
        """
        Test that None encoding returns False.
        @athena: 754f1a1a689c
        """
        mock_stdout.encoding = None
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli.os.environ", {})
    @patch("tasktree.cli.os.name", "posix")
    @patch("tasktree.cli.sys.stdout")
    def test_supports_unicode_with_latin1_encoding(self, mock_stdout):
        """
        Test that Latin-1 encoding returns False (can't encode symbols).
        @athena: f3f546227173
        """
        mock_stdout.encoding = "latin-1"
        self.assertFalse(_supports_unicode())

    @patch("tasktree.cli._supports_unicode")
    def test_get_action_success_string_with_unicode(self, mock_supports):
        """
        Test success string returns Unicode symbol when supported.
        @athena: 3324caf800fe
        """
        mock_supports.return_value = True
        self.assertEqual(get_action_success_string(), "✓")

    @patch("tasktree.cli._supports_unicode")
    def test_get_action_success_string_without_unicode(self, mock_supports):
        """
        Test success string returns ASCII when Unicode not supported.
        @athena: cf3ca8a0a9ca
        """
        mock_supports.return_value = False
        self.assertEqual(get_action_success_string(), "[ OK ]")

    @patch("tasktree.cli._supports_unicode")
    def test_get_action_failure_string_with_unicode(self, mock_supports):
        """
        Test failure string returns Unicode symbol when supported.
        @athena: 5ba096e1f387
        """
        mock_supports.return_value = True
        self.assertEqual(get_action_failure_string(), "✗")

    @patch("tasktree.cli._supports_unicode")
    def test_get_action_failure_string_without_unicode(self, mock_supports):
        """
        Test failure string returns ASCII when Unicode not supported.
        @athena: 39b7731083e5
        """
        mock_supports.return_value = False
        self.assertEqual(get_action_failure_string(), "[ FAIL ]")


class TestTaskOutputParameter(unittest.TestCase):
    """
    Test task_output CLI parameter handling.
    @athena: 27cbf2313636
    """

    def test_task_output_accepts_all(self):
        """
        Test that task_output parameter accepts "all" value.
        @athena: a9873d058150
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
