"""Logging infrastructure for Task Tree.

Provides a Logger interface for dependency injection of logging functionality.
"""

from __future__ import annotations

import enum
from abc import abstractmethod


class LogLevel(enum.Enum):
    """
    Log verbosity levels for tasktree diagnostic messages.

    Lower numeric values represent higher severity / less verbosity.
    @athena: 3b2d8a378440
    """

    FATAL = 0  # Only unrecoverable errors (malformed task files, missing dependencies)
    ERROR = 1  # Fatal errors plus task execution failures
    WARN = 2  # Errors plus warnings about deprecated features, configuration issues
    INFO = 3  # Warnings plus normal execution progress (default)
    DEBUG = 4  # Info plus variable values, resolved paths, environment details
    TRACE = 5  # Debug plus fine-grained execution tracing


class Logger:
    """
    Abstract base class for logging implementations.

    Provides a level-based logging interface with stack-based level management.
    Concrete implementations must define how messages are output (e.g., to console, file, etc.).
    @athena: fdcd08796011
    """

    @abstractmethod
    def log(self, level: LogLevel, *args, **kwargs) -> None:
        """
        Log a message at the specified level.

        Args:
        level: The severity level of the message
        *args: Positional arguments to log (strings, Rich objects, etc.)
        **kwargs: Keyword arguments for formatting (e.g., style, justify)
        @athena: 4563ae920ff4
        """
        pass

    @abstractmethod
    def push_level(self, level: LogLevel) -> None:
        """
        Push a new log level onto the level stack.

        Messages below this level will be filtered out until pop_level() is called.
        Useful for temporarily increasing verbosity in specific code sections.

        Args:
        level: The new log level to use
        @athena: c73ac375d30a
        """
        pass

    @abstractmethod
    def pop_level(self) -> LogLevel:
        """
        Pop the current log level from the stack and return to the previous level.

        Returns:
        The log level that was popped

        Raises:
        RuntimeError: If attempting to pop the base (initial) log level
        @athena: d4721a34516f
        """
        pass

    def fatal(self, *args, **kwargs):
        """
        @athena: 951c9c5d4f3b
        """
        self.log(LogLevel.FATAL, *args, **kwargs)

    def error(self, *args, **kwargs):
        """
        @athena: 7125264a8ce1
        """
        self.log(LogLevel.ERROR, *args, **kwargs)

    def warn(self, *args, **kwargs):
        """
        @athena: 5a70af1bb5b4
        """
        self.log(LogLevel.WARN, *args, **kwargs)

    def info(self, *args, **kwargs):
        """
        @athena: cdb5381023a6
        """
        self.log(LogLevel.INFO, *args, **kwargs)

    def debug(self, *args, **kwargs):
        """
        @athena: ddfd0e359f09
        """
        self.log(LogLevel.DEBUG, *args, **kwargs)

    def trace(self, *args, **kwargs):
        """
        @athena: 4f615a15562c
        """
        self.log(LogLevel.TRACE, *args, **kwargs)
