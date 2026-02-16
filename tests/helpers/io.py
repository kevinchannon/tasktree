"""I/O helper functions for tests."""

import re


def strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI escape sequences from text.

    This is useful for testing CLI output that may contain color codes.
    """
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)
