"""Tests for LSP position utilities."""

import unittest
from lsprotocol.types import Position
from tasktree.lsp.position_utils import (
    is_in_cmd_field,
    get_prefix_at_position,
    get_task_at_position,
)


class TestIsInCmdField(unittest.TestCase):
    """Tests for is_in_cmd_field function."""

    def test_position_in_cmd_field(self):
        """Test that position inside cmd field value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo {{ tt."
        # Position at the end of the cmd line (after the space following 'cmd:')
        position = Position(line=2, character=9)
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
        self.assertEqual(prefix, "    cmd: echo {{ tt.proj")

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


class TestGetTaskAtPosition(unittest.TestCase):
    """Tests for get_task_at_position function."""

    def test_position_in_task_cmd(self):
        """Test getting task name when position is in cmd field."""
        text = """tasks:
  build:
    cmd: echo {{ arg.name }}
"""
        # Position in cmd field of 'build' task
        position = Position(line=2, character=15)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "build")

    def test_position_in_task_deps(self):
        """Test getting task name when position is in deps field."""
        text = """tasks:
  deploy:
    deps: [build]
    cmd: echo deploying
"""
        # Position in deps field of 'deploy' task
        position = Position(line=2, character=10)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "deploy")

    def test_position_on_task_name_line(self):
        """Test getting task name when position is on task name line."""
        text = """tasks:
  build:
    cmd: echo hello
"""
        # Position on the 'build:' line
        position = Position(line=1, character=5)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "build")

    def test_position_in_second_task(self):
        """Test getting task name for second task in file."""
        text = """tasks:
  build:
    cmd: echo building
  deploy:
    cmd: echo deploying
"""
        # Position in 'deploy' task cmd
        position = Position(line=4, character=15)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "deploy")

    def test_position_outside_tasks(self):
        """Test that position outside tasks section returns None."""
        text = """variables:
  foo: bar
tasks:
  build:
    cmd: echo hello
"""
        # Position in variables section
        position = Position(line=1, character=5)
        task_name = get_task_at_position(text, position)
        self.assertIsNone(task_name)

    def test_position_in_multiline_cmd(self):
        """Test getting task name in multiline cmd field.

        Multiline cmd fields (using | or >) span multiple lines.
        The task name should be found by looking for the most recent
        task definition before the cursor position.
        """
        text = """tasks:
  build:
    cmd: |
      echo line 1
      echo line 2
"""
        # Position on second line of multiline cmd (line 4, after "build:" on line 1)
        position = Position(line=4, character=10)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "build")

    def test_position_in_multiline_cmd_folded(self):
        """Test getting task name in multiline cmd with folded style (>)."""
        text = """tasks:
  deploy:
    cmd: >
      docker run
      --rm
      myapp:latest
"""
        # Position on third line of multiline cmd
        char_offset = len("      myapp:")
        position = Position(line=5, character=char_offset)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "deploy")

    def test_position_out_of_bounds(self):
        """Test that out of bounds position returns None."""
        text = """tasks:
  build:
    cmd: echo hello
"""
        # Position beyond document
        position = Position(line=10, character=0)
        task_name = get_task_at_position(text, position)
        self.assertIsNone(task_name)

    def test_unicode_task_name(self):
        """Test getting task name with Unicode characters (emojis)."""
        text = """tasks:
  🐳🏃‍♂️‍➡️:
    cmd: echo running
"""
        # Position in cmd field of Unicode task
        position = Position(line=2, character=10)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🐳🏃‍♂️‍➡️")

    def test_unicode_task_name_with_umbrella(self):
        """Test getting task name with Unicode emoji argument."""
        text = """tasks:
  🦊:
    args: [🌂]
    cmd: echo {{arg.🌂}}
"""
        # Position in cmd field
        position = Position(line=3, character=15)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")

    def test_exotic_yaml_single_line_braces(self):
        """Test getting task name from exotic YAML with braces on single line."""
        text = """tasks: {🦊: {args: [🌂], cmd: "echo {{arg.🌂}}"}}"""
        # Position in the middle of the single-line YAML (in the cmd value)
        position = Position(line=0, character=40)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")

    def test_four_space_indentation(self):
        """Test getting task name with 4-space indentation."""
        text = """tasks:
    build:
        cmd: echo building
"""
        # Position in cmd field
        position = Position(line=2, character=15)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "build")

    def test_no_indentation_flow_style(self):
        """Test getting task name with flow style (no indentation)."""
        text = """tasks: {deploy: {cmd: "echo deploying"}}"""
        # Position in cmd value
        position = Position(line=0, character=30)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "deploy")

    def test_mixed_unicode_and_ascii(self):
        """Test file with both Unicode and ASCII task names."""
        text = """tasks:
  build-🐳:
    cmd: echo docker build
  deploy:
    cmd: echo deploy
"""
        # Position in first task
        position1 = Position(line=2, character=10)
        task_name1 = get_task_at_position(text, position1)
        self.assertEqual(task_name1, "build-🐳")

        # Position in second task
        position2 = Position(line=4, character=10)
        task_name2 = get_task_at_position(text, position2)
        self.assertEqual(task_name2, "deploy")

    def test_incomplete_yaml_missing_closing_quote(self):
        """Test getting task name from incomplete YAML (missing closing quote).

        LSP servers must handle incomplete YAML gracefully since users type
        incrementally. This test ensures we can still detect the task name
        even when the YAML is syntactically incomplete.
        """
        text = """tasks: {🦊: {args: [🌂], cmd: "echo {{arg."""
        # Position after {{arg. - should still detect we're in task 🦊
        position = Position(line=0, character=45)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")

    def test_incomplete_yaml_with_complete_template(self):
        """Test getting task name from incomplete YAML with complete template marker.

        Even when the outer YAML structure is incomplete, if the template
        marker is complete ({{arg.}}), we should still detect the task.
        """
        text = """tasks: {🦊: {args: [🌂], cmd: "echo {{arg.}}"""
        # Position inside the template (after {{arg.)
        position = Position(line=0, character=45)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")


if __name__ == "__main__":
    unittest.main()
