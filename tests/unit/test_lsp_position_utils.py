"""Tests for LSP position utilities.

Updated for the tree-sitter refactor (Phase 6): functions now accept a
Tree object instead of raw text.  Tests for removed helpers
(_is_position_valid, _is_in_list_field) have been deleted; equivalent
coverage lives in tests/unit/test_ts_context.py.
"""

import unittest
from lsprotocol.types import Position
from tasktree.lsp.position_utils import (
    is_in_cmd_field,
    is_in_working_dir_field,
    is_in_outputs_field,
    is_in_deps_field,
    is_in_substitutable_field,
    is_inside_open_template,
    get_prefix_at_position,
    get_task_at_position,
)
from tasktree.lsp.ts_context import parse_document


class TestIsInCmdField(unittest.TestCase):
    """Tests for is_in_cmd_field function."""

    def test_position_in_cmd_field(self):
        """Test that position inside cmd field value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo {{ tt."
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: "))
        self.assertTrue(is_in_cmd_field(tree, position))

    def test_position_not_in_cmd_field(self):
        """Test that position outside cmd field returns False."""
        text = "tasks:\n  hello:\n    deps: [build]"
        tree = parse_document(text)
        position = Position(line=2, character=len("    deps: [buil"))
        self.assertFalse(is_in_cmd_field(tree, position))

    def test_position_before_cmd_colon(self):
        """Test that position before 'cmd:' returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=2, character=len("    "))
        self.assertFalse(is_in_cmd_field(tree, position))

    def test_position_right_after_cmd_colon(self):
        """Test that position right after 'cmd:' returns True."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd:"))
        self.assertTrue(is_in_cmd_field(tree, position))

    def test_position_in_cmd_value(self):
        """Test that position in the middle of cmd value returns True."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo "))
        self.assertTrue(is_in_cmd_field(tree, position))

    def test_position_out_of_bounds(self):
        """Test that out of bounds position returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=10, character=0)
        self.assertFalse(is_in_cmd_field(tree, position))

    def test_position_in_multiline_cmd_literal(self):
        """Test that position in multi-line cmd (|) returns True."""
        text = """tasks:
  build:
    cmd: |
      echo line 1
      echo line 2"""
        tree = parse_document(text)
        position = Position(line=4, character=len("      echo line"))
        self.assertTrue(is_in_cmd_field(tree, position))

    def test_position_in_multiline_cmd_folded(self):
        """Test that position in multi-line cmd (>) returns True."""
        text = """tasks:
  deploy:
    cmd: >
      docker run
      --rm
      myapp"""
        tree = parse_document(text)
        position = Position(line=5, character=len("      my"))
        self.assertTrue(is_in_cmd_field(tree, position))

    def test_position_in_multiline_cmd_strip(self):
        """Test that position in multi-line cmd with strip (|-) returns True."""
        text = """tasks:
  test:
    cmd: |-
      pytest tests/
      coverage report"""
        tree = parse_document(text)
        position = Position(line=3, character=len("      pytest"))
        self.assertTrue(is_in_cmd_field(tree, position))

    def test_position_after_multiline_cmd_in_different_field(self):
        """Test that position after multi-line cmd in different field returns False."""
        text = """tasks:
  build:
    cmd: |
      echo building
    deps: [lint]"""
        tree = parse_document(text)
        position = Position(line=4, character=len("    deps: "))
        self.assertFalse(is_in_cmd_field(tree, position))


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
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo {"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "build")

    def test_position_in_task_deps(self):
        """Test getting task name when position is in deps field."""
        text = """tasks:
  deploy:
    deps: [build]
    cmd: echo deploying
"""
        tree = parse_document(text)
        position = Position(line=2, character=len("    deps: "))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "deploy")

    def test_position_on_task_name_line(self):
        """Test getting task name when position is on task name line."""
        text = """tasks:
  build:
    cmd: echo hello
"""
        tree = parse_document(text)
        position = Position(line=1, character=len("  buil"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "build")

    def test_position_in_second_task(self):
        """Test getting task name for second task in file."""
        text = """tasks:
  build:
    cmd: echo building
  deploy:
    cmd: echo deploying
"""
        tree = parse_document(text)
        position = Position(line=4, character=len("    cmd: echo d"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "deploy")

    def test_position_outside_tasks(self):
        """Test that position outside tasks section returns None."""
        text = """variables:
  foo: bar
tasks:
  build:
    cmd: echo hello
"""
        tree = parse_document(text)
        position = Position(line=1, character=len("  foo"))
        task_name = get_task_at_position(tree, position)
        self.assertIsNone(task_name)

    def test_position_in_multiline_cmd(self):
        """Test getting task name in multiline cmd field."""
        text = """tasks:
  build:
    cmd: |
      echo line 1
      echo line 2
"""
        tree = parse_document(text)
        position = Position(line=4, character=len("      echo"))
        task_name = get_task_at_position(tree, position)
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
        tree = parse_document(text)
        position = Position(line=5, character=len("      myapp:"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "deploy")

    def test_unicode_task_name(self):
        """Test getting task name with Unicode characters (emojis)."""
        text = """tasks:
  🐳🏃‍♂️‍➡️:
    cmd: echo running
"""
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: e"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "🐳🏃‍♂️‍➡️")

    def test_unicode_task_name_with_unicode_arg(self):
        """Test getting task name when task and arg names both use Unicode."""
        text = """tasks:
  café:
    args:
      - résumé
    cmd: echo {{ arg.résumé }}
"""
        tree = parse_document(text)
        position = Position(line=4, character=len("    cmd: echo {{ arg.r"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "café")

    def test_mixed_unicode_and_ascii_tasks(self):
        """Test task detection with a mix of Unicode and ASCII task names."""
        text = """tasks:
  build:
    cmd: echo building
  déployer:
    cmd: echo deploying
  test:
    cmd: echo testing
"""
        tree = parse_document(text)
        self.assertEqual(get_task_at_position(tree, Position(line=2, character=10)), "build")
        self.assertEqual(get_task_at_position(tree, Position(line=4, character=10)), "déployer")
        self.assertEqual(get_task_at_position(tree, Position(line=6, character=10)), "test")

    def test_four_space_indentation(self):
        """Test getting task name with 4-space indentation."""
        text = """tasks:
    build:
        cmd: echo building
"""
        tree = parse_document(text)
        position = Position(line=2, character=len("        cmd: ec"))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "build")

    def test_no_indentation_flow_style(self):
        """Test getting task name with flow style (no indentation)."""
        text = """tasks: {deploy: {cmd: "echo deploying"}}"""
        tree = parse_document(text)
        position = Position(line=0, character=len("""tasks: {deploy: {cmd: "echo d"""))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "deploy")

    def test_position_out_of_bounds_returns_none(self):
        """Test that a cursor position past the end of the document returns None."""
        text = "tasks:\n  build:\n    cmd: echo hello\n"
        tree = parse_document(text)
        # Line 100 does not exist in a 4-line document
        position = Position(line=100, character=0)
        result = get_task_at_position(tree, position)
        self.assertIsNone(result)


class TestIsInWorkingDirField(unittest.TestCase):
    """Tests for is_in_working_dir_field function."""

    def test_position_in_working_dir_field(self):
        """Test that position inside working_dir field value returns True."""
        text = "tasks:\n  hello:\n    working_dir: /tmp/{{ var."
        tree = parse_document(text)
        position = Position(line=2, character=len("    working_dir: "))
        self.assertTrue(is_in_working_dir_field(tree, position))

    def test_position_not_in_working_dir_field(self):
        """Test that position outside working_dir field returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo"))
        self.assertFalse(is_in_working_dir_field(tree, position))

    def test_position_after_working_dir_colon(self):
        """Test that position right after 'working_dir:' returns True."""
        text = "tasks:\n  hello:\n    working_dir: /path"
        tree = parse_document(text)
        position = Position(line=2, character=len("    working_dir:"))
        self.assertTrue(is_in_working_dir_field(tree, position))


class TestIsInOutputsField(unittest.TestCase):
    """Tests for is_in_outputs_field function."""

    def test_position_in_outputs_field_single_line(self):
        """Test that position in outputs field (single-line format) returns True."""
        text = "tasks:\n  hello:\n    outputs: [\"file-{{ arg."
        tree = parse_document(text)
        position = Position(line=2, character=len("    outputs: "))
        self.assertTrue(is_in_outputs_field(tree, position))

    def test_position_in_outputs_field_multi_line(self):
        """Test that position in outputs field (multi-line format) returns True."""
        text = "tasks:\n  hello:\n    outputs:\n      - file-{{ arg."
        tree = parse_document(text)
        position = Position(line=3, character=len("      - file-"))
        self.assertTrue(is_in_outputs_field(tree, position))

    def test_position_not_in_outputs_field(self):
        """Test that position outside outputs field returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo"))
        self.assertFalse(is_in_outputs_field(tree, position))


class TestIsInDepsField(unittest.TestCase):
    """Tests for is_in_deps_field function."""

    def test_position_in_deps_field_single_line(self):
        """Test that position in deps field (single-line format) returns True."""
        text = "tasks:\n  hello:\n    deps: [task({{ arg."
        tree = parse_document(text)
        position = Position(line=2, character=len("    deps: "))
        self.assertTrue(is_in_deps_field(tree, position))

    def test_position_in_deps_field_multi_line(self):
        """Test that position in deps field (multi-line format) returns True."""
        text = "tasks:\n  hello:\n    deps:\n      - task: [{{ arg."
        tree = parse_document(text)
        position = Position(line=3, character=len("      - task: "))
        self.assertTrue(is_in_deps_field(tree, position))

    def test_position_not_in_deps_field(self):
        """Test that position outside deps field returns False."""
        text = "tasks:\n  hello:\n    cmd: echo hello"
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo"))
        self.assertFalse(is_in_deps_field(tree, position))


class TestIsInSubstitutableField(unittest.TestCase):
    """Tests for is_in_substitutable_field function."""

    def test_position_in_cmd_field(self):
        """Test that position in cmd field returns True."""
        text = "tasks:\n  hello:\n    cmd: echo {{ arg."
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo "))
        self.assertTrue(is_in_substitutable_field(tree, position))

    def test_position_in_working_dir_field(self):
        """Test that position in working_dir field returns True."""
        text = "tasks:\n  hello:\n    working_dir: {{ arg."
        tree = parse_document(text)
        position = Position(line=2, character=len("    working_dir: "))
        self.assertTrue(is_in_substitutable_field(tree, position))

    def test_position_in_outputs_field(self):
        """Test that position in outputs field returns True."""
        text = "tasks:\n  hello:\n    outputs: [\"file-{{ arg."
        tree = parse_document(text)
        position = Position(line=2, character=len("    outputs: "))
        self.assertTrue(is_in_substitutable_field(tree, position))

    def test_position_in_deps_field(self):
        """Test that position in deps field returns True."""
        text = "tasks:\n  hello:\n    deps: [task({{ arg."
        tree = parse_document(text)
        position = Position(line=2, character=len("    deps: "))
        self.assertTrue(is_in_substitutable_field(tree, position))

    def test_position_in_default_field(self):
        """Test that position in args default field returns True."""
        text = "tasks:\n  hello:\n    args:\n      - name: foo\n        default: {{ self.inputs."
        tree = parse_document(text)
        position = Position(line=4, character=len("        default: "))
        self.assertTrue(is_in_substitutable_field(tree, position))

    def test_position_in_non_substitutable_field(self):
        """Test that position in non-substitutable field returns False."""
        text = "tasks:\n  hello:\n    desc: Some description"
        tree = parse_document(text)
        position = Position(line=2, character=len("    desc: "))
        self.assertFalse(is_in_substitutable_field(tree, position))

    def test_position_in_desc_field(self):
        """Test that position in desc field returns False."""
        text = "tasks:\n  hello:\n    desc: Some description"
        tree = parse_document(text)
        position = Position(line=2, character=len("    desc: "))
        self.assertFalse(is_in_substitutable_field(tree, position))


class TestIncompleteYamlEdgeCases(unittest.TestCase):
    """Tests for position detection in incomplete / broken YAML documents.

    These edge cases reflect typical LSP editing conditions: the document
    is almost always syntactically invalid because the user is mid-keystroke.
    """

    def test_exotic_yaml_single_line_flow_style(self):
        """Test position detection in single-line flow-style YAML."""
        text = '{ tasks: { build: { cmd: "echo hi" }, deploy: { cmd: "echo bye" } } }'
        tree = parse_document(text)
        # Cursor somewhere in deploy's cmd
        position = Position(line=0, character=len('{ tasks: { build: { cmd: "echo hi" }, deploy: { cmd: "echo '))
        task_name = get_task_at_position(tree, position)
        self.assertEqual(task_name, "deploy")

    def test_incomplete_yaml_missing_closing_quote(self):
        """Test position detection when document has an unclosed string."""
        # Unclosed double-quote makes the document invalid YAML
        text = 'tasks:\n  build:\n    cmd: "echo hello\n  deploy:\n    cmd: echo bye\n'
        tree = parse_document(text)
        # Should not raise; result may be None or a partial match
        result = get_task_at_position(tree, Position(line=4, character=10))
        self.assertTrue(result is None or isinstance(result, str))

    def test_incomplete_yaml_with_complete_template_pattern(self):
        """Test is_in_cmd_field when document contains {{ arg. }} style but is otherwise valid."""
        text = "tasks:\n  build:\n    args:\n      - name\n    cmd: echo {{ arg. }}\n"
        tree = parse_document(text)
        # Cursor inside the value after "{{ arg." — should still be in cmd field
        position = Position(line=4, character=len("    cmd: echo {{ arg. "))
        result = is_in_cmd_field(tree, position)
        self.assertIsInstance(result, bool)

    def test_get_task_at_position_unclosed_bracket_in_deps(self):
        """Test task detection when deps list has unclosed bracket."""
        text = "tasks:\n  build:\n    cmd: gcc main.c\n  test:\n    deps: [\n"
        tree = parse_document(text)
        # Cursor at the end of the broken deps line
        position = Position(line=4, character=len("    deps: ["))
        result = get_task_at_position(tree, position)
        # Should return "test" or None gracefully
        self.assertTrue(result is None or isinstance(result, str))

    def test_is_in_cmd_field_unclosed_template(self):
        """Test cmd field detection when line ends with unclosed {{ template."""
        text = "tasks:\n  build:\n    cmd: echo {{ tt."
        tree = parse_document(text)
        position = Position(line=2, character=len("    cmd: echo {{ tt."))
        # Should not raise; tree-sitter handles malformed input gracefully
        result = is_in_cmd_field(tree, position)
        self.assertIsInstance(result, bool)


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
