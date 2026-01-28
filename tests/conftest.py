"""Pytest fixtures for Task Tree tests."""

import pytest

from tasktree.logging import LoggerFn


@pytest.fixture
def logger_fn() -> LoggerFn:
    """Provide a no-op logger function for tests.

    Returns:
        A LoggerFn that discards all output (useful for testing).
    """
    return lambda *args, **kwargs: None
