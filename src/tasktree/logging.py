"""Logging infrastructure for Task Tree.

Provides a Logger class for outputting messages to the console.
"""

from __future__ import annotations

from rich.console import Console


class Logger:
    """Logger for outputting messages to the console.

    This class wraps Rich's Console to provide a consistent logging interface
    throughout the application.
    """

    def __init__(self, console: Console):
        """Initialize the logger with a Rich console.

        Args:
            console: Rich Console instance for output
        """
        self.console = console

    def log(self, message: str) -> None:
        """Log a message to the console.

        Args:
            message: The message to log
        """
        self.console.print(message)
