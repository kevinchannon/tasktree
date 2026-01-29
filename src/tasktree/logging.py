"""Logging infrastructure for Task Tree.

Provides a Logger interface for dependency injection of logging functionality.
"""

from __future__ import annotations

import enum
from abc import abstractmethod


class LogLevel(enum.Enum):
    """Log verbosity levels for tasktree diagnostic messages.

    Lower numeric values represent higher severity / less verbosity.
    """

    FATAL = 0  # Only unrecoverable errors (malformed task files, missing dependencies)
    ERROR = 1  # Fatal errors plus task execution failures
    WARN = 2  # Errors plus warnings about deprecated features, configuration issues
    INFO = 3  # Warnings plus normal execution progress (default)
    DEBUG = 4  # Info plus variable values, resolved paths, environment details
    TRACE = 5  # Debug plus fine-grained execution tracing


class Logger:
    @abstractmethod
    def log(self, level: LogLevel, *args, **kwargs) -> None:
        pass

    @abstractmethod
    def push_level(self, level: LogLevel) -> None:
        pass

    @abstractmethod
    def pop_level(self) -> LogLevel:
        pass

    def fatal(self, *args, **kwargs):
        self.log(LogLevel.FATAL, *args, **kwargs)

    def error(self, *args, **kwargs):
        self.log(LogLevel.ERROR, *args, **kwargs)

    def warn(self, *args, **kwargs):
        self.log(LogLevel.WARN, *args, **kwargs)

    def info(self, *args, **kwargs):
        self.log(LogLevel.INFO, *args, **kwargs)

    def debug(self, *args, **kwargs):
        self.log(LogLevel.DEBUG, *args, **kwargs)

    def trace(self, *args, **kwargs):
        self.log(LogLevel.TRACE, *args, **kwargs)
