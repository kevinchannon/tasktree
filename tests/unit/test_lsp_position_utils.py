"""Tests for LSP position utilities."""

import unittest
from lsprotocol.types import Position
from tasktree.lsp.position_utils import (
    is_in_cmd_field,
    is_in_working_dir_field,
    is_in_substitutable_field,
    get_prefix_at_position,
    get_task_at_position,
)


class TestIsInCmdField(unittest.TestCase):
    """Tests for is_in_cmd_field function."""

    def test_position_in_cmd_field(self):
        """Test that position inside cmd field value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo {{ tt."
        position = Position(line=2, character=len("    cmd: "))
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_not_in_cmd_field(self):
        """Test that position outside cmd field returns False."""
        text = "tasks:\n  hello:\n    deps: [build]"
        position = Position(line=2, character=len("    deps: [buil"))
        self.assertFalse(is_in_cmd_field(text, position))

    def test_position_before_cmd_colon(self):
        """Test that position before 'cmd:' returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    "))
        self.assertFalse(is_in_cmd_field(text, position))

    def test_position_right_after_cmd_colon(self):
        """Test that position right after 'cmd:' returns True."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    cmd:"))
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_in_cmd_value(self):
        """Test that position in the middle of cmd value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    cmd: echo "))
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
        position = Position(line=2, character=len("    cmd: echo {{ tt.proj"))
        prefix = get_prefix_at_position(text, position)
        self.assertEqual(prefix, "    cmd: echo {{ tt.proj")

    def test_get_prefix_at_end(self):
        """Test getting prefix at end of line."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    cmd: echo hello"))
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
        position = Position(line=2, character=len("    cmd: echo {"))
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "build")

    def test_position_in_task_deps(self):
        """Test getting task name when position is in deps field."""
        text = """tasks:
  deploy:
    deps: [build]
    cmd: echo deploying
"""
        position = Position(line=2, character=len("    deps: "))
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "deploy")

    def test_position_on_task_name_line(self):
        """Test getting task name when position is on task name line."""
        text = """tasks:
  build:
    cmd: echo hello
"""
        position = Position(line=1, character=len("  buil"))
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
        position = Position(line=4, character=len("    cmd: echo d"))
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
        position = Position(line=1, character=len("  foo"))
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
        position = Position(line=4, character=len("      echo"))
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
        position = Position(line=2, character=len("    cmd: e"))
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🐳🏃‍♂️‍➡️")

    def test_unicode_task_name_with_umbrella(self):
        """Test getting task name with Unicode emoji argument."""
        text = """tasks:
  🦊:
    args: [🌂]
    cmd: echo {{arg.🌂}}
"""
        position = Position(line=3, character=len("    cmd: echo {"))
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")

    def test_exotic_yaml_single_line_braces(self):
        """Test getting task name from exotic YAML with braces on single line."""
        text = """tasks: {🦊: {args: [🌂], cmd: "echo {{arg.🌂}}"}}"""
        position = Position(line=0, character=len("""tasks: {🦊: {args: [🌂], cmd: "echo {{ar"""))
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")

    def test_four_space_indentation(self):
        """Test getting task name with 4-space indentation."""
        text = """tasks:
    build:
        cmd: echo building
"""
        position = Position(line=2, character=len("        cmd: ec"))
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "build")

    def test_no_indentation_flow_style(self):
        """Test getting task name with flow style (no indentation)."""
        text = """tasks: {deploy: {cmd: "echo deploying"}}"""
        position = Position(line=0, character=len("""tasks: {deploy: {cmd: "echo d"""))
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
        position1 = Position(line=2, character=len("    cmd: e"))
        task_name1 = get_task_at_position(text, position1)
        self.assertEqual(task_name1, "build-🐳")

        position2 = Position(line=4, character=len("    cmd: e"))
        task_name2 = get_task_at_position(text, position2)
        self.assertEqual(task_name2, "deploy")

    def test_incomplete_yaml_missing_closing_quote(self):
        """Test getting task name from incomplete YAML (missing closing quote).

        LSP servers must handle incomplete YAML gracefully since users type
        incrementally. This test ensures we can still detect the task name
        even when the YAML is syntactically incomplete.
        """
        text = """tasks: {🦊: {args: [🌂], cmd: "echo {{arg."""
        char_offset = len("""tasks: {🦊: {args: [🌂], cmd: "echo {{arg.""")
        position = Position(line=0, character=char_offset)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")

    def test_incomplete_yaml_with_complete_template(self):
        """Test getting task name from incomplete YAML with complete template marker.

        Even when the outer YAML structure is incomplete, if the template
        marker is complete ({{arg.}}), we should still detect the task.
        """
        text = """tasks: {🦊: {args: [🌂], cmd: "echo {{arg.}}"""
        char_offset = len("""tasks: {🦊: {args: [🌂], cmd: "echo {{arg.""")
        position = Position(line=0, character=char_offset)
        task_name = get_task_at_position(text, position)
        self.assertEqual(task_name, "🦊")


class TestIsInWorkingDirField(unittest.TestCase):
    """Tests for is_in_working_dir_field function."""

    def test_position_in_working_dir_field(self):
        """Test that position inside working_dir field value returns True."""
        text = "tasks:\n  hello:\n    working_dir: /tmp/{{ var."
        position = Position(line=2, character=len("    working_dir: "))
        self.assertTrue(is_in_working_dir_field(text, position))

    def test_position_not_in_working_dir_field(self):
        """Test that position outside working_dir field returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    cmd: echo"))
        self.assertFalse(is_in_working_dir_field(text, position))

    def test_position_after_working_dir_colon(self):
        """Test that position right after 'working_dir:' returns True."""
        text = "tasks:\n  hello:\n    working_dir: /path"
        position = Position(line=2, character=len("    working_dir:"))
        self.assertTrue(is_in_working_dir_field(text, position))


class TestIsInOutputsField(unittest.TestCase):
    """Tests for is_in_outputs_field function."""

    def test_position_in_outputs_field_single_line(self):
        """Test that position in outputs field (single-line format) returns True."""
        text = "tasks:\n  hello:\n    outputs: [\"file-{{ arg."
        position = Position(line=2, character=len("    outputs: "))
        from tasktree.lsp.position_utils import is_in_outputs_field
        self.assertTrue(is_in_outputs_field(text, position))

    def test_position_in_outputs_field_multi_line(self):
        """Test that position in outputs field (multi-line format) returns True."""
        text = "tasks:\n  hello:\n    outputs:\n      - file-{{ arg."
        position = Position(line=3, character=len("      - file-"))
        from tasktree.lsp.position_utils import is_in_outputs_field
        self.assertTrue(is_in_outputs_field(text, position))

    def test_position_not_in_outputs_field(self):
        """Test that position outside outputs field returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    cmd: echo"))
        from tasktree.lsp.position_utils import is_in_outputs_field
        self.assertFalse(is_in_outputs_field(text, position))


class TestIsInDepsField(unittest.TestCase):
    """Tests for is_in_deps_field function."""

    def test_position_in_deps_field_single_line(self):
        """Test that position in deps field (single-line format) returns True."""
        text = "tasks:\n  hello:\n    deps: [task({{ arg."
        position = Position(line=2, character=len("    deps: "))
        from tasktree.lsp.position_utils import is_in_deps_field
        self.assertTrue(is_in_deps_field(text, position))

    def test_position_in_deps_field_multi_line(self):
        """Test that position in deps field (multi-line format) returns True."""
        text = "tasks:\n  hello:\n    deps:\n      - task: [{{ arg."
        position = Position(line=3, character=len("      - task: "))
        from tasktree.lsp.position_utils import is_in_deps_field
        self.assertTrue(is_in_deps_field(text, position))

    def test_position_not_in_deps_field(self):
        """Test that position outside deps field returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        position = Position(line=2, character=len("    cmd: echo"))
        from tasktree.lsp.position_utils import is_in_deps_field
        self.assertFalse(is_in_deps_field(text, position))


class TestIsInSubstitutableField(unittest.TestCase):
    """Tests for is_in_substitutable_field function."""

    def test_position_in_cmd_field(self):
        """Test that position in cmd field returns True."""
        text = "tasks:\n  hello:\n    cmd: echo {{ arg."
        position = Position(line=2, character=len("    cmd: echo "))
        self.assertTrue(is_in_substitutable_field(text, position))

    def test_position_in_working_dir_field(self):
        """Test that position in working_dir field returns True."""
        text = "tasks:\n  hello:\n    working_dir: {{ arg."
        position = Position(line=2, character=len("    working_dir: "))
        self.assertTrue(is_in_substitutable_field(text, position))

    def test_position_in_outputs_field(self):
        """Test that position in outputs field returns True."""
        text = "tasks:\n  hello:\n    outputs: [\"file-{{ arg."
        position = Position(line=2, character=len("    outputs: "))
        self.assertTrue(is_in_substitutable_field(text, position))

    def test_position_in_deps_field(self):
        """Test that position in deps field returns True."""
        text = "tasks:\n  hello:\n    deps: [task({{ arg."
        position = Position(line=2, character=len("    deps: "))
        self.assertTrue(is_in_substitutable_field(text, position))

    def test_position_in_default_field(self):
        """Test that position in args default field returns True."""
        text = "tasks:\n  hello:\n    args:\n      - name: foo\n        default: {{ self.inputs."
        position = Position(line=4, character=len("        default: "))
        self.assertTrue(is_in_substitutable_field(text, position))

    def test_position_in_non_substitutable_field(self):
        """Test that position in non-substitutable field returns False."""
        text = "tasks:\n  hello:\n    deps: [build]"
        position = Position(line=2, character=len("    deps: "))
        self.assertFalse(is_in_substitutable_field(text, position))

    def test_position_in_desc_field(self):
        """Test that position in desc field returns False."""
        text = "tasks:\n  hello:\n    desc: Some description"
        position = Position(line=2, character=len("    desc: "))
        self.assertFalse(is_in_substitutable_field(text, position))


if __name__ == "__main__":
    unittest.main()
