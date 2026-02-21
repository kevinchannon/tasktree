"""Tests for LSP position utilities."""

import unittest
from lsprotocol.types import Position
from tasktree.lsp.position_utils import (
    is_in_cmd_field,
    is_in_working_dir_field,
    is_in_substitutable_field,
    is_inside_open_template,
    get_prefix_at_position,
    get_task_at_position,
    _is_in_list_field,
    _is_position_valid,
)


class TestIsPositionValid(unittest.TestCase):
    """Tests for _is_position_valid helper function."""

    def test_valid_position(self):
        """Test that valid position returns lines and line."""
        text = "tasks:\n  hello:\n    cmd: echo"
        position = Position(line=2, character=5)
        result = _is_position_valid(text, position)
        self.assertIsNotNone(result)
        lines, line = result
        self.assertEqual(len(lines), 3)
        self.assertEqual(line, "    cmd: echo")

    def test_position_out_of_bounds(self):
        """Test that position beyond document returns None."""
        text = "tasks:\n  hello:\n    cmd: echo"
        position = Position(line=10, character=0)
        result = _is_position_valid(text, position)
        self.assertIsNone(result)

    def test_position_beyond_line_length(self):
        """Test that position beyond line length returns None."""
        text = "tasks:\n  hello:\n    cmd: echo"
        position = Position(line=2, character=100)
        result = _is_position_valid(text, position)
        self.assertIsNone(result)

    def test_position_at_end_of_line(self):
        """Test that position at end of line (after last char) is valid."""
        text = "tasks:\n  hello:\n    cmd: echo"
        position = Position(line=2, character=len("    cmd: echo"))
        result = _is_position_valid(text, position)
        self.assertIsNotNone(result)


class TestIsInListField(unittest.TestCase):
    """Tests for _is_in_list_field helper function."""

    def test_position_in_single_line_format(self):
        """Test that position in single-line format returns True."""
        text = "tasks:\n  hello:\n    outputs: [\"file.txt\"]"
        position = Position(line=2, character=len("    outputs: "))
        self.assertTrue(_is_in_list_field(text, position, "outputs"))

    def test_position_in_multi_line_format(self):
        """Test that position in multi-line format returns True."""
        text = "tasks:\n  hello:\n    outputs:\n      - file.txt"
        position = Position(line=3, character=len("      - file"))
        self.assertTrue(_is_in_list_field(text, position, "outputs"))

    def test_position_before_field_name(self):
        """Test that position before field name returns False."""
        text = "tasks:\n  hello:\n    outputs: [\"file.txt\"]"
        position = Position(line=2, character=len("    "))
        self.assertFalse(_is_in_list_field(text, position, "outputs"))

    def test_position_in_different_field(self):
        """Test that position in different field returns False."""
        text = "tasks:\n  hello:\n    deps: [task1]"
        position = Position(line=2, character=len("    deps: "))
        self.assertFalse(_is_in_list_field(text, position, "outputs"))

    def test_position_out_of_bounds(self):
        """Test that out of bounds position returns False."""
        text = "tasks:\n  hello:\n    outputs: []"
        position = Position(line=10, character=0)
        self.assertFalse(_is_in_list_field(text, position, "outputs"))

    def test_position_beyond_line_length(self):
        """Test that position beyond line length returns False."""
        text = "tasks:\n  hello:\n    outputs: []"
        position = Position(line=2, character=100)
        self.assertFalse(_is_in_list_field(text, position, "outputs"))

    def test_generic_field_name_inputs(self):
        """Test that helper works for 'inputs' field."""
        text = "tasks:\n  hello:\n    inputs: [\"*.txt\"]"
        position = Position(line=2, character=len("    inputs: "))
        self.assertTrue(_is_in_list_field(text, position, "inputs"))

    def test_generic_field_name_deps(self):
        """Test that helper works for 'deps' field."""
        text = "tasks:\n  hello:\n    deps: [task1]"
        position = Position(line=2, character=len("    deps: "))
        self.assertTrue(_is_in_list_field(text, position, "deps"))

    def test_multi_line_list_item_before_dash(self):
        """Test that position before dash in list item returns False."""
        text = "tasks:\n  hello:\n    outputs:\n      - file.txt"
        position = Position(line=3, character=len("    "))
        self.assertFalse(_is_in_list_field(text, position, "outputs"))

    def test_multi_line_list_item_after_dash(self):
        """Test that position after dash in list item returns True."""
        text = "tasks:\n  hello:\n    outputs:\n      - file.txt"
        position = Position(line=3, character=len("      - "))
        self.assertTrue(_is_in_list_field(text, position, "outputs"))


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

    def test_position_in_multiline_cmd_literal(self):
        """Test that position in multi-line cmd (|) returns True."""
        text = """tasks:
  build:
    cmd: |
      echo line 1
      echo line 2"""
        # Position on second line of multi-line cmd
        position = Position(line=4, character=len("      echo line"))
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_in_multiline_cmd_folded(self):
        """Test that position in multi-line cmd (>) returns True."""
        text = """tasks:
  deploy:
    cmd: >
      docker run
      --rm
      myapp"""
        # Position on third line of multi-line cmd
        position = Position(line=5, character=len("      my"))
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_in_multiline_cmd_strip(self):
        """Test that position in multi-line cmd with strip (|-) returns True."""
        text = """tasks:
  test:
    cmd: |-
      pytest tests/
      coverage report"""
        # Position on first line of multi-line cmd content
        position = Position(line=3, character=len("      pytest"))
        self.assertTrue(is_in_cmd_field(text, position))

    def test_position_after_multiline_cmd_in_different_field(self):
        """Test that position after multi-line cmd in different field returns False."""
        text = """tasks:
  build:
    cmd: |
      echo building
    deps: [lint]"""
        # Position in deps field (after multi-line cmd)
        position = Position(line=4, character=len("    deps: "))
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
        """Test that position in non-substitutable field returns False.

        Note: deps and outputs fields ARE substitutable (for parameterized deps
        and templated output paths), even if they don't currently contain templates.
        This test uses the 'desc' field which is never substitutable.
        """
        text = "tasks:\n  hello:\n    desc: Some description"
        position = Position(line=2, character=len("    desc: "))
        self.assertFalse(is_in_substitutable_field(text, position))

    def test_position_in_desc_field(self):
        """Test that position in desc field returns False."""
        text = "tasks:\n  hello:\n    desc: Some description"
        position = Position(line=2, character=len("    desc: "))
        self.assertFalse(is_in_substitutable_field(text, position))


class TestIsInsideOpenTemplate(unittest.TestCase):
    """Tests for is_inside_open_template function."""

    def test_no_template_returns_false(self):
        """Test that plain text with no {{ returns False."""
        self.assertFalse(is_inside_open_template("  - build"))

    def test_open_double_brace_only_returns_true(self):
        """Test that bare {{ with no closing }} returns True."""
        self.assertTrue(is_inside_open_template("    cmd: echo {{"))

    def test_open_template_with_prefix_returns_true(self):
        """Test that {{ tt. without closing }} returns True."""
        self.assertTrue(is_inside_open_template("    cmd: echo {{ tt."))

    def test_closed_template_returns_false(self):
        """Test that a fully closed {{ }} template returns False."""
        self.assertFalse(is_inside_open_template("    cmd: echo {{ tt.task_name }}"))

    def test_closed_template_then_open_returns_true(self):
        """Test detection when a closed template is followed by a new open one."""
        self.assertTrue(is_inside_open_template("    cmd: {{ tt.a }} and {{ var."))

    def test_empty_prefix_returns_false(self):
        """Test that empty string returns False."""
        self.assertFalse(is_inside_open_template(""))

    def test_open_template_at_start_of_deps_item(self):
        """Test that {{ at start of a deps list item returns True."""
        self.assertTrue(is_inside_open_template("  - {{"))

    def test_open_template_with_arg_prefix(self):
        """Test that {{ arg. prefix is detected as inside open template."""
        self.assertTrue(is_inside_open_template("  - dep_task({{ arg.env"))


if __name__ == "__main__":
    unittest.main()
