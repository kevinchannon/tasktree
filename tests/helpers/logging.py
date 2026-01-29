from tasktree.logging import Logger, LogLevel


class LoggerStub(Logger):
    def log(self, _level: LogLevel, *args, **kwargs) -> None:
        pass


logger_stub = LoggerStub()
