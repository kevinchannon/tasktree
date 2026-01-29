from tasktree.logging import Logger, LogLevel
from rich.console import Console


class ConsoleLogger(Logger):
    def __init__(self, console: Console, level: LogLevel = LogLevel.INFO) -> None:
        self._console = console
        self._levels = [level]

    def log(self, level: LogLevel = LogLevel.INFO, *args, **kwargs) -> None:
        if self._levels[-1].value >= level.value:
            self._console.print(*args, **kwargs)

    def push_level(self, level: LogLevel) -> None:
        self._levels.append(level)

    def pop_level(self) -> None:
        self._levels.pop()
