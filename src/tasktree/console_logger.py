from tasktree.logging import Logger, LogLevel
from rich.console import Console


class ConsoleLogger(Logger):
    """Console-based logger implementation using Rich for formatting.

    Filters log messages based on the current log level. Messages with severity
    lower than the current level are suppressed. Supports a stack-based level
    management system for temporary verbosity changes.
    """

    def __init__(self, console: Console, level: LogLevel = LogLevel.INFO) -> None:
        """Initialize the console logger.

        Args:
            console: Rich Console instance to use for output
            level: Initial log level (default: INFO)
        """
        self._console = console
        self._levels = [level]

    def log(self, level: LogLevel = LogLevel.INFO, *args, **kwargs) -> None:
        """Log a message to the console if it meets the current level threshold.

        Messages are only printed if their level is at or above the current level
        (i.e., level.value <= current_level.value, since lower values = higher severity).

        Args:
            level: The severity level of this message (default: INFO)
            *args: Positional arguments passed to Rich Console.print()
            **kwargs: Keyword arguments passed to Rich Console.print()
        """
        if self._levels[-1].value >= level.value:
            self._console.print(*args, **kwargs)

    def push_level(self, level: LogLevel) -> None:
        """Push a new log level onto the stack.

        Args:
            level: The new log level to activate
        """
        self._levels.append(level)

    def pop_level(self) -> LogLevel:
        """Pop the current log level and return to the previous level.

        Returns:
            The log level that was popped

        Raises:
            RuntimeError: If attempting to pop the base (initial) log level
        """
        if len(self._levels) <= 1:
            raise RuntimeError("Cannot pop the base log level")
        return self._levels.pop()
