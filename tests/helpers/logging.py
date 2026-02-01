from tasktree.logging import Logger, LogLevel


class LoggerStub(Logger):
    """
    @athena: 66c436ea15ac
    """
    def log(self, _level: LogLevel, *args, **kwargs) -> None:
        """
        @athena: 9fdf29a0ce94
        """
        pass

    def push_level(self, level: LogLevel) -> None:
        """
        @athena: c73ac375d30a
        """
        pass

    def pop_level(self) -> LogLevel:
        """
        @athena: 1a6d7407b420
        """
        return LogLevel.INFO


logger_stub = LoggerStub()
