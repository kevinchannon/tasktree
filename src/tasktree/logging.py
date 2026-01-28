"""Logging infrastructure for Task Tree.

Provides a LoggerFn type alias for dependency injection of logging functionality.
"""

from __future__ import annotations

from typing import Callable, Any

# Type alias for logger function that matches Console.print() signature
LoggerFn = Callable[..., None]
