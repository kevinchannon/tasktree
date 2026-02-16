"""CLI command implementations and shared utilities."""

from __future__ import annotations

import os
import sys


def _supports_unicode() -> bool:
    """
    Check if the terminal supports Unicode characters.

    Returns:
    True if terminal supports UTF-8, False otherwise
    @athena: 68f62a942a95
    """
    # Hard stop: classic Windows console (conhost)
    if os.name == "nt" and "WT_SESSION" not in os.environ:
        return False

    # Encoding check
    encoding = sys.stdout.encoding
    if not encoding:
        return False

    try:
        "✓✗".encode(encoding)
        return True
    except UnicodeEncodeError:
        return False


def get_action_success_string() -> str:
    """
    Get the appropriate success symbol based on terminal capabilities.

    Returns:
    Unicode tick symbol (✓) if terminal supports UTF-8, otherwise "[ OK ]"
    @athena: 39d9966ee6c8
    """
    return "✓" if _supports_unicode() else "[ OK ]"


def get_action_failure_string() -> str:
    """
    Get the appropriate failure symbol based on terminal capabilities.

    Returns:
    Unicode cross symbol (✗) if terminal supports UTF-8, otherwise "[ FAIL ]"
    @athena: 5dd1111f8d74
    """
    return "✗" if _supports_unicode() else "[ FAIL ]"
