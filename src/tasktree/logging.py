"""Logging infrastructure for Task Tree.

Provides a LoggerFn type alias for dependency injection of logging functionality.
"""

from __future__ import annotations

import enum
from typing import Callable, Any

# Type alias for logger function that matches Console.print() signature
LoggerFn = Callable[..., None]


class LogLevel(enum.Enum):
    """Log verbosity levels for tasktree diagnostic messages.

    Lower numeric values represent higher severity / less verbosity.
    """
    FATAL = 0  # Only unrecoverable errors (malformed task files, missing dependencies)
    ERROR = 1  # Fatal errors plus task execution failures
    WARN = 2   # Errors plus warnings about deprecated features, configuration issues
    INFO = 3   # Warnings plus normal execution progress (default)
    DEBUG = 4  # Info plus variable values, resolved paths, environment details
    TRACE = 5  # Debug plus fine-grained execution tracing


def make_leveled_logger(base_logger: LoggerFn, current_level: LogLevel) -> LoggerFn:
    """Create a logger function with level filtering.

    Args:
        base_logger: The underlying logger function (e.g., console.print)
        current_level: The minimum log level to display

    Returns:
        A logger function that accepts an optional 'level' keyword argument.
        If the message level is below current_level, the message is suppressed.

    Example:
        logger = make_leveled_logger(console.print, LogLevel.INFO)
        logger("Normal message", level=LogLevel.INFO)  # Shown
        logger("Debug message", level=LogLevel.DEBUG)  # Suppressed (DEBUG > INFO)
    """
    def leveled_logger(*args, level: LogLevel = LogLevel.INFO, **kwargs) -> None:
        # Only log if message level <= current_level (lower values = higher priority)
        if level.value <= current_level.value:
            base_logger(*args, **kwargs)

    return leveled_logger
