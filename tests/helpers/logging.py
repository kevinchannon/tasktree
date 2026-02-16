from tasktree.logging import Logger, LogLevel


class LoggerStub(Logger):
    """
    """

    def log(self, _level: LogLevel, *args, **kwargs) -> None:
        """
        """
        pass

    def push_level(self, level: LogLevel) -> None:
        """
        """
        pass

    def pop_level(self) -> LogLevel:
        """
        """
        return LogLevel.INFO


logger_stub = LoggerStub()
