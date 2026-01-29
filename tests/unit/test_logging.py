"""Unit tests for logging module."""

import unittest
from unittest.mock import Mock, MagicMock, call

from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree

from tasktree.console_logger import ConsoleLogger
from tasktree.logging import LogLevel


class TestConsoleLogger(unittest.TestCase):
    """Tests for ConsoleLogger implementation."""

    def setUp(self):
        self._console = MagicMock()
        self._console.print = MagicMock()

        self._logger = ConsoleLogger(self._console)

    def test_logger_fn_accepts_no_arguments(self):
        """Test that Logger can be called with no arguments."""
        self._logger.log(LogLevel.INFO)
        self._console.print.assert_called_once_with()

    def test_logger_fn_accepts_string_message(self):
        """Test that LoggerFn can be called with string messages."""
        self._logger.log(LogLevel.INFO, "test message")
        self._console.print.assert_called_once_with("test message")

    def test_logger_fn_accepts_multiple_string_arguments(self):
        """Test that LoggerFn can be called with multiple string arguments."""
        self._logger.log(LogLevel.INFO, "first", "second", "third")
        self._console.print.assert_called_once_with("first", "second", "third")

    def test_logger_fn_accepts_rich_table(self):
        """Test that LoggerFn can be called with Rich Table objects."""

        table = Table(title="Test Table")
        table.add_column("Column 1")
        table.add_row("Row 1")

        self._logger.log(LogLevel.INFO, table)
        self._console.print.assert_called_once_with(table)

    def test_logger_accepts_rich_syntax(self):
        """Test that Logger can be called with Rich Syntax objects."""
        syntax = Syntax("print('hello')", "python")

        self._logger.log(LogLevel.INFO, syntax)
        self._console.print.assert_called_once_with(syntax)

    def test_logger_accepts_rich_tree(self):
        """Test that Logger can be called with Rich Tree objects."""
        tree = Tree("Root")
        tree.add("Child 1")
        tree.add("Child 2")

        self._logger.log(LogLevel.INFO, tree)
        self._console.print.assert_called_once_with(tree)

    def test_logger_accepts_kwargs(self):
        """Test that LoggerFn can be called with keyword arguments."""
        self._logger.log(LogLevel.INFO, "message", style="bold", justify="center")
        self._console.print.assert_called_once_with(
            "message", style="bold", justify="center"
        )

    def test_logger_accepts_args_and_kwargs(self):
        """Test that Logger can be called with both args and kwargs."""
        self._logger.log(LogLevel.INFO, "msg1", "msg2", style="red", end="")
        self._console.print.assert_called_once_with("msg1", "msg2", style="red", end="")


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


class TestLoggerLevels(unittest.TestCase):
    """Tests for make_leveled_logger function."""

    def setUp(self):
        self._console = MagicMock()
        self._console.print = MagicMock()

    def test_filters_messages_below_threshold(self):
        """Test that messages below the current level are filtered out."""
        l = ConsoleLogger(self._console, LogLevel.ERROR)
        l.info("msg")

        self._console.print.assert_not_called()

        l.error("error!")
        self._console.print.assert_called_once_with("error!")

    def test_shows_messages_at_or_above_threshold(self):
        """Test that messages at or above the current level are shown."""
        l = ConsoleLogger(self._console, LogLevel.ERROR)

        l.error("error!")
        l.fatal("fatal!!")
        self._console.print.assert_has_calls([call("error!"), call("fatal!!")])

    def test_push_and_pop_levels(self):
        l = ConsoleLogger(self._console, LogLevel.INFO)

        l.info("should see info 1")
        l.debug("should not see debug 1")
        l.push_level(LogLevel.DEBUG)
        l.debug("should see debug 2")
        l.trace("should not see trace 1")
        l.push_level(LogLevel.TRACE)
        l.trace("should see trace 2")
        l.pop_level()  # Back to debug level
        l.trace("should not see trace 3")
        l.debug("should see debug 3")
        l.pop_level()  # Back to info
        l.debug("should not see debug 1")
        l.info("should see info 2")

        self._console.print.assert_has_calls(
            [
                call("should see info 1"),
                call("should see debug 2"),
                call("should see trace 2"),
                call("should see debug 3"),
                call("should see info 2"),
            ]
        )

    def test_pop_level_returns_popped_level(self):
        """Test that pop_level() returns the level that was popped."""
        l = ConsoleLogger(self._console, LogLevel.INFO)
        l.push_level(LogLevel.DEBUG)
        l.push_level(LogLevel.TRACE)

        popped = l.pop_level()
        self.assertEqual(popped, LogLevel.TRACE)

        popped = l.pop_level()
        self.assertEqual(popped, LogLevel.DEBUG)

    def test_pop_level_raises_when_popping_base_level(self):
        """Test that pop_level() raises RuntimeError when trying to pop the base level."""
        l = ConsoleLogger(self._console, LogLevel.INFO)

        with self.assertRaises(RuntimeError) as context:
            l.pop_level()

        self.assertIn("Cannot pop the base log level", str(context.exception))

    def test_pop_level_allows_multiple_pushes_then_pops(self):
        """Test that pop_level() works correctly after multiple pushes."""
        l = ConsoleLogger(self._console, LogLevel.INFO)

        # Push multiple levels
        l.push_level(LogLevel.DEBUG)
        l.push_level(LogLevel.TRACE)
        l.push_level(LogLevel.ERROR)

        # Pop them all back
        self.assertEqual(l.pop_level(), LogLevel.ERROR)
        self.assertEqual(l.pop_level(), LogLevel.TRACE)
        self.assertEqual(l.pop_level(), LogLevel.DEBUG)

        # Now trying to pop again should raise
        with self.assertRaises(RuntimeError):
            l.pop_level()


if __name__ == "__main__":
    unittest.main()
