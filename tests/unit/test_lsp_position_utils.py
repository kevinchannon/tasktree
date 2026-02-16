"""Tests for LSP position utilities."""

import unittest
from lsprotocol.types import Position
from tasktree.lsp.position_utils import is_in_cmd_field, get_prefix_at_position


class TestIsInCmdField(unittest.TestCase):
    """Tests for is_in_cmd_field function."""

    def test_position_in_cmd_field(self):
        """Test that position inside cmd field value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo {{ tt."
        # Position at the end of the cmd line
        position = Position(line=2, character=25)
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_not_in_cmd_field(self):
        """Test that position outside cmd field returns False."""
        text = "tasks:\n  hello:\n    deps: [build]"
        # Position in deps field
        position = Position(line=2, character=15)
        self.assertFalse(is_in_cmd_field(text, position))

    def test_position_before_cmd_colon(self):
        """Test that position before 'cmd:' returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        # Position at 'c' in 'cmd'
        position = Position(line=2, character=4)
        self.assertFalse(is_in_cmd_field(text, position))

    def test_position_right_after_cmd_colon(self):
        """Test that position right after 'cmd:' returns True."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        # Position right after 'cmd:'
        position = Position(line=2, character=8)
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_in_cmd_value(self):
        """Test that position in the middle of cmd value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        # Position at 'h' in 'hello'
        position = Position(line=2, character=14)
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_out_of_bounds(self):
        """Test that out of bounds position returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        # Position beyond document
        position = Position(line=10, character=0)
        self.assertFalse(is_in_cmd_field(text, position))


class TestGetPrefixAtPosition(unittest.TestCase):
    """Tests for get_prefix_at_position function."""

    def test_get_prefix_at_middle(self):
        """Test getting prefix in the middle of a line."""
        text = "tasks:\n  hello:\n    cmd: echo {{ tt.project"
        position = Position(line=2, character=24)
        prefix = get_prefix_at_position(text, position)
        self.assertEqual(prefix, "    cmd: echo {{ tt.")

    def test_get_prefix_at_end(self):
        """Test getting prefix at end of line."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=23)
        prefix = get_prefix_at_position(text, position)
        self.assertEqual(prefix, "    cmd: echo hello")

    def test_get_prefix_at_start(self):
        """Test getting prefix at start of line."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=0)
        prefix = get_prefix_at_position(text, position)
        self.assertEqual(prefix, "")

    def test_get_prefix_out_of_bounds(self):
        """Test getting prefix for out of bounds position."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=10, character=0)
        prefix = get_prefix_at_position(text, position)
        self.assertEqual(prefix, "")


if __name__ == "__main__":
    unittest.main()
