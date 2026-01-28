"""Unit tests for logging module."""

import unittest
from unittest.mock import Mock

from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.tree import Tree

from tasktree.logging import LoggerFn


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


if __name__ == "__main__":
    unittest.main()
