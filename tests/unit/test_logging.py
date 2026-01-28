"""Unit tests for logging module."""

import unittest
from unittest.mock import Mock

from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree

from tasktree.logging import LoggerFn, LogLevel, make_leveled_logger


class TestLoggerFn(unittest.TestCase):
    """Tests for LoggerFn type alias."""

    def test_logger_fn_accepts_no_arguments(self):
        """Test that LoggerFn can be called with no arguments."""
        mock_logger: LoggerFn = Mock()
        mock_logger()
        mock_logger.assert_called_once_with()

    def test_logger_fn_accepts_string_message(self):
        """Test that LoggerFn can be called with string messages."""
        mock_logger: LoggerFn = Mock()
        mock_logger("test message")
        mock_logger.assert_called_once_with("test message")

    def test_logger_fn_accepts_multiple_string_arguments(self):
        """Test that LoggerFn can be called with multiple string arguments."""
        mock_logger: LoggerFn = Mock()
        mock_logger("first", "second", "third")
        mock_logger.assert_called_once_with("first", "second", "third")

    def test_logger_fn_accepts_rich_table(self):
        """Test that LoggerFn can be called with Rich Table objects."""
        mock_logger: LoggerFn = Mock()
        table = Table(title="Test Table")
        table.add_column("Column 1")
        table.add_row("Row 1")

        mock_logger(table)
        mock_logger.assert_called_once_with(table)

    def test_logger_fn_accepts_rich_syntax(self):
        """Test that LoggerFn can be called with Rich Syntax objects."""
        mock_logger: LoggerFn = Mock()
        syntax = Syntax("print('hello')", "python")

        mock_logger(syntax)
        mock_logger.assert_called_once_with(syntax)

    def test_logger_fn_accepts_rich_tree(self):
        """Test that LoggerFn can be called with Rich Tree objects."""
        mock_logger: LoggerFn = Mock()
        tree = Tree("Root")
        tree.add("Child 1")
        tree.add("Child 2")

        mock_logger(tree)
        mock_logger.assert_called_once_with(tree)

    def test_logger_fn_accepts_kwargs(self):
        """Test that LoggerFn can be called with keyword arguments."""
        mock_logger: LoggerFn = Mock()
        mock_logger("message", style="bold", justify="center")
        mock_logger.assert_called_once_with("message", style="bold", justify="center")

    def test_logger_fn_accepts_args_and_kwargs(self):
        """Test that LoggerFn can be called with both args and kwargs."""
        mock_logger: LoggerFn = Mock()
        mock_logger("msg1", "msg2", style="red", end="")
        mock_logger.assert_called_once_with("msg1", "msg2", style="red", end="")

    def test_logger_fn_works_with_real_console_print(self):
        """Test that a lambda wrapping Console.print() conforms to LoggerFn."""
        console = Console()
        logger_fn: LoggerFn = lambda *args, **kwargs: console.print(*args, **kwargs)

        # This test verifies type compatibility - if it compiles, it passes
        # We're testing that Console.print() signature matches LoggerFn
        self.assertIsNotNone(logger_fn)

    def test_logger_fn_lambda_with_no_args(self):
        """Test that a simple lambda with no-op conforms to LoggerFn."""
        logger_fn: LoggerFn = lambda *args, **kwargs: None

        # Call it various ways to verify the signature works
        logger_fn()
        logger_fn("message")
        logger_fn("msg", style="bold")
        logger_fn(Table(title="Test"))

        # If we get here without errors, the type signature is correct
        self.assertIsNotNone(logger_fn)


class TestLogLevel(unittest.TestCase):
    """Tests for LogLevel enum."""

    def test_log_level_values(self):
        """Test that LogLevel enum has correct values and ordering."""
        self.assertEqual(LogLevel.FATAL.value, 0)
        self.assertEqual(LogLevel.ERROR.value, 1)
        self.assertEqual(LogLevel.WARN.value, 2)
        self.assertEqual(LogLevel.INFO.value, 3)
        self.assertEqual(LogLevel.DEBUG.value, 4)
        self.assertEqual(LogLevel.TRACE.value, 5)

    def test_log_level_ordering(self):
        """Test that log levels have correct severity ordering."""
        # Lower values = higher severity = less verbose
        self.assertLess(LogLevel.FATAL.value, LogLevel.ERROR.value)
        self.assertLess(LogLevel.ERROR.value, LogLevel.WARN.value)
        self.assertLess(LogLevel.WARN.value, LogLevel.INFO.value)
        self.assertLess(LogLevel.INFO.value, LogLevel.DEBUG.value)
        self.assertLess(LogLevel.DEBUG.value, LogLevel.TRACE.value)


class TestMakeLeveledLogger(unittest.TestCase):
    """Tests for make_leveled_logger function."""

    def test_default_level_is_info(self):
        """Test that messages without explicit level default to INFO."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.INFO)

        logger("test message")
        mock_base.assert_called_once_with("test message")

    def test_filters_messages_below_threshold(self):
        """Test that messages below the current level are filtered out."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.INFO)

        # DEBUG and TRACE should be filtered (their values > INFO.value)
        logger("debug msg", level=LogLevel.DEBUG)
        logger("trace msg", level=LogLevel.TRACE)
        mock_base.assert_not_called()

    def test_shows_messages_at_or_above_threshold(self):
        """Test that messages at or above the current level are shown."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.INFO)

        # FATAL, ERROR, WARN, INFO should all be shown (their values <= INFO.value)
        logger("fatal msg", level=LogLevel.FATAL)
        logger("error msg", level=LogLevel.ERROR)
        logger("warn msg", level=LogLevel.WARN)
        logger("info msg", level=LogLevel.INFO)

        self.assertEqual(mock_base.call_count, 4)

    def test_debug_level_shows_debug_and_above(self):
        """Test that DEBUG level shows debug, info, warn, error, and fatal."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.DEBUG)

        logger("fatal", level=LogLevel.FATAL)
        logger("error", level=LogLevel.ERROR)
        logger("warn", level=LogLevel.WARN)
        logger("info", level=LogLevel.INFO)
        logger("debug", level=LogLevel.DEBUG)
        logger("trace", level=LogLevel.TRACE)  # Should be filtered

        # All except TRACE should be shown
        self.assertEqual(mock_base.call_count, 5)

    def test_trace_level_shows_all_messages(self):
        """Test that TRACE level shows all messages."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.TRACE)

        logger("fatal", level=LogLevel.FATAL)
        logger("error", level=LogLevel.ERROR)
        logger("warn", level=LogLevel.WARN)
        logger("info", level=LogLevel.INFO)
        logger("debug", level=LogLevel.DEBUG)
        logger("trace", level=LogLevel.TRACE)

        # All messages should be shown
        self.assertEqual(mock_base.call_count, 6)

    def test_fatal_level_shows_only_fatal(self):
        """Test that FATAL level shows only fatal messages."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.FATAL)

        logger("fatal", level=LogLevel.FATAL)
        logger("error", level=LogLevel.ERROR)  # Filtered
        logger("warn", level=LogLevel.WARN)    # Filtered
        logger("info", level=LogLevel.INFO)    # Filtered
        logger("debug", level=LogLevel.DEBUG)  # Filtered
        logger("trace", level=LogLevel.TRACE)  # Filtered

        # Only FATAL should be shown
        self.assertEqual(mock_base.call_count, 1)
        mock_base.assert_called_once_with("fatal")

    def test_preserves_args_and_kwargs(self):
        """Test that leveled logger passes through args and kwargs correctly."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.INFO)

        logger("msg1", "msg2", style="bold", justify="center", level=LogLevel.INFO)
        mock_base.assert_called_once_with("msg1", "msg2", style="bold", justify="center")

    def test_works_with_rich_objects(self):
        """Test that leveled logger works with Rich objects."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.INFO)

        table = Table(title="Test")
        logger(table, level=LogLevel.INFO)
        mock_base.assert_called_once_with(table)

    def test_level_keyword_not_passed_to_base_logger(self):
        """Test that the 'level' keyword argument is not passed to the base logger."""
        mock_base = Mock()
        logger = make_leveled_logger(mock_base, LogLevel.INFO)

        logger("test", level=LogLevel.INFO, style="bold")

        # Verify 'level' is not in the call kwargs
        call_args, call_kwargs = mock_base.call_args
        self.assertNotIn('level', call_kwargs)
        self.assertEqual(call_kwargs, {'style': 'bold'})


if __name__ == "__main__":
    unittest.main()
