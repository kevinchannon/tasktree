"""Unit tests for the tree-sitter context module (ts_context.py)."""

import tempfile
import unittest
from pathlib import Path

from tasktree.lsp.ts_context import (
    parse_document,
    get_task_at_position,
    is_in_field,
    is_in_substitutable_field,
    extract_variables,
    extract_task_args,
    extract_task_inputs,
    extract_task_outputs,
    extract_task_names,
)


# ---------------------------------------------------------------------------
# parse_document
# ---------------------------------------------------------------------------


class TestParseDocument(unittest.TestCase):
    def test_returns_tree_for_valid_yaml(self):
        tree = parse_document("tasks:\n  build:\n    cmd: echo hello\n")
        self.assertIsNotNone(tree)
        self.assertIsNotNone(tree.root_node)

    def test_returns_tree_for_empty_text(self):
        tree = parse_document("")
        self.assertIsNotNone(tree)

    def test_returns_tree_for_broken_yaml(self):
        tree = parse_document("{ tasks: { build: { cmd: echo ")
        self.assertIsNotNone(tree)

    def test_returns_tree_for_severely_broken_yaml(self):
        text = '{ variables: { foo: "bar }, tasks: { task-1: { cmd: echo "hello" }, task-2: {    deps:   ['
        tree = parse_document(text)
        self.assertIsNotNone(tree)


# ---------------------------------------------------------------------------
# get_task_at_position
# ---------------------------------------------------------------------------


class TestGetTaskAtPosition(unittest.TestCase):
    BLOCK_YAML = (
        "tasks:\n"
        "  compile:\n"
        "    cmd: gcc main.c\n"
        "  link:\n"
        "    cmd: ld main.o\n"
        "  build:\n"
        "    deps:\n"
        "      - compile\n"
    )

    def _tree(self, text):
        return parse_document(text)

    def test_returns_task_when_cursor_in_cmd(self):
        tree = self._tree("tasks:\n  build:\n    cmd: echo hello\n")
        result = get_task_at_position(tree, 2, 10)
        self.assertEqual(result, "build")

    def test_returns_correct_task_for_multiple_tasks(self):
        tree = self._tree(self.BLOCK_YAML)
        # Cursor in compile's cmd line
        self.assertEqual(get_task_at_position(tree, 2, 10), "compile")
        # Cursor in link's cmd line
        self.assertEqual(get_task_at_position(tree, 4, 10), "link")
        # Cursor in build's deps
        self.assertEqual(get_task_at_position(tree, 7, 8), "build")

    def test_returns_none_when_no_tasks_section(self):
        tree = self._tree("variables:\n  foo: bar\n")
        self.assertIsNone(get_task_at_position(tree, 1, 5))

    def test_returns_none_for_empty_document(self):
        tree = self._tree("")
        self.assertIsNone(get_task_at_position(tree, 0, 0))

    def test_returns_task_for_flow_style(self):
        tree = self._tree(
            "{ tasks: { task-1: { cmd: echo hello }, task-2: { cmd: hi } } }"
        )
        # In flow-style, task-2 starts later in the line
        # task-1 is at column ~11, task-2 is at column ~40
        result = get_task_at_position(tree, 0, 50)
        self.assertEqual(result, "task-2")

    def test_returns_none_for_broken_yaml_no_tasks(self):
        tree = self._tree("{ variables: { foo: bar } }")
        self.assertIsNone(get_task_at_position(tree, 0, 0))

    def test_handles_severely_broken_yaml(self):
        text = '{ variables: { foo: "bar }, tasks: { task-1: { cmd: echo "hello" }, task-2: {    deps:   ['
        tree = parse_document(text)
        # Should not raise; may return None or a partial result
        result = get_task_at_position(tree, 0, 80)
        # Just verify it doesn't crash
        self.assertTrue(result is None or isinstance(result, str))


# ---------------------------------------------------------------------------
# is_in_field
# ---------------------------------------------------------------------------


class TestIsInField(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_cursor_in_cmd_value(self):
        tree = self._tree("tasks:\n  build:\n    cmd: echo hello\n")
        self.assertTrue(is_in_field(tree, 2, 10, "cmd"))

    def test_cursor_on_cmd_key_not_in_value(self):
        tree = self._tree("tasks:\n  build:\n    cmd: echo hello\n")
        # Position 4 is on "cmd" itself (before the colon)
        self.assertFalse(is_in_field(tree, 2, 4, "cmd"))

    def test_cursor_in_working_dir_value(self):
        tree = self._tree("tasks:\n  build:\n    working_dir: /tmp\n")
        self.assertTrue(is_in_field(tree, 2, 18, "working_dir"))

    def test_cursor_in_deps_value_flow(self):
        tree = self._tree("tasks:\n  build:\n    deps: [compile]\n")
        self.assertTrue(is_in_field(tree, 2, 15, "deps"))

    def test_cursor_in_deps_block(self):
        text = "tasks:\n  build:\n    deps:\n      - compile\n"
        tree = self._tree(text)
        # Cursor on "compile" at line 3
        self.assertTrue(is_in_field(tree, 3, 8, "deps"))

    def test_cursor_not_in_field_wrong_name(self):
        tree = self._tree("tasks:\n  build:\n    cmd: echo hello\n")
        self.assertFalse(is_in_field(tree, 2, 10, "deps"))

    def test_broken_yaml_does_not_crash(self):
        tree = self._tree("{ tasks: { build: { cmd: echo ")
        # Should not raise
        result = is_in_field(tree, 0, 25, "cmd")
        self.assertIsInstance(result, bool)

    def test_empty_document_returns_false(self):
        tree = self._tree("")
        self.assertFalse(is_in_field(tree, 0, 0, "cmd"))


# ---------------------------------------------------------------------------
# is_in_substitutable_field
# ---------------------------------------------------------------------------


class TestIsInSubstitutableField(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_cmd_is_substitutable(self):
        tree = self._tree("tasks:\n  build:\n    cmd: echo hello\n")
        self.assertTrue(is_in_substitutable_field(tree, 2, 10))

    def test_working_dir_is_substitutable(self):
        tree = self._tree("tasks:\n  build:\n    working_dir: /tmp\n")
        self.assertTrue(is_in_substitutable_field(tree, 2, 18))

    def test_outputs_is_substitutable(self):
        tree = self._tree("tasks:\n  build:\n    outputs:\n      - dist/app\n")
        self.assertTrue(is_in_substitutable_field(tree, 3, 8))

    def test_deps_is_substitutable(self):
        text = "tasks:\n  build:\n    deps:\n      - compile\n"
        tree = self._tree(text)
        self.assertTrue(is_in_substitutable_field(tree, 3, 8))

    def test_default_field_is_substitutable(self):
        text = (
            "tasks:\n  build:\n    args:\n"
            "      - conf_path: { default: value }\n"
        )
        tree = self._tree(text)
        # Cursor somewhere after "default: " on line 3
        self.assertTrue(is_in_substitutable_field(tree, 3, 32))

    def test_desc_field_is_not_substitutable(self):
        tree = self._tree("tasks:\n  build:\n    desc: hello\n")
        self.assertFalse(is_in_substitutable_field(tree, 2, 12))

    def test_empty_document_returns_false(self):
        tree = self._tree("")
        self.assertFalse(is_in_substitutable_field(tree, 0, 0))


# ---------------------------------------------------------------------------
# extract_variables
# ---------------------------------------------------------------------------


class TestExtractVariables(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_extracts_simple_variables(self):
        text = "variables:\n  foo: bar\n  baz: qux\n"
        result = extract_variables(self._tree(text))
        self.assertEqual(result, ["baz", "foo"])

    def test_extracts_complex_variables(self):
        text = (
            "variables:\n"
            "  simple: value\n"
            "  from_env:\n"
            "    env: HOME\n"
            "  from_eval:\n"
            '    eval: "echo hi"\n'
        )
        result = extract_variables(self._tree(text))
        self.assertEqual(sorted(result), ["from_env", "from_eval", "simple"])

    def test_no_variables_section(self):
        result = extract_variables(self._tree("tasks:\n  build:\n    cmd: hi\n"))
        self.assertEqual(result, [])

    def test_empty_document(self):
        result = extract_variables(self._tree(""))
        self.assertEqual(result, [])

    def test_broken_yaml(self):
        result = extract_variables(self._tree("{ variables: { foo: bar"), )
        # May or may not find the variable; should not raise
        self.assertIsInstance(result, list)

    def test_severely_broken_yaml(self):
        text = '{ variables: { foo: "bar }, tasks: {'
        result = extract_variables(parse_document(text))
        self.assertIsInstance(result, list)

    def test_incomplete_yaml_unclosed_template_in_variable_value(self):
        """Variables section remains parseable even with unclosed {{ in a value."""
        text = "variables:\n  foo: bar\n  baz: value {{ var.\ntasks:\n  build:\n    cmd: echo\n"
        result = extract_variables(parse_document(text))
        # foo and baz should be found (tree-sitter recovers)
        self.assertIsInstance(result, list)

    def test_incomplete_yaml_missing_value(self):
        """Variables section with a key but no value (cursor right after colon)."""
        text = "variables:\n  foo:\ntasks:\n  build:\n    cmd: echo\n"
        result = extract_variables(parse_document(text))
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# extract_task_args
# ---------------------------------------------------------------------------


class TestExtractTaskArgs(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_string_format_args(self):
        text = "tasks:\n  build:\n    args:\n      - name\n      - version\n"
        result = extract_task_args(self._tree(text), "build")
        self.assertEqual(result, ["name", "version"])

    def test_dict_format_args(self):
        text = (
            "tasks:\n  build:\n    args:\n"
            "      - build_type:\n"
            '          default: "debug"\n'
            "      - target:\n"
            "          type: str\n"
        )
        result = extract_task_args(self._tree(text), "build")
        self.assertEqual(result, ["build_type", "target"])

    def test_mixed_format_args(self):
        text = (
            "tasks:\n  build:\n    args:\n"
            "      - name\n"
            "      - build_type:\n"
            '          default: "debug"\n'
            "      - version\n"
        )
        result = extract_task_args(self._tree(text), "build")
        self.assertEqual(result, ["build_type", "name", "version"])

    def test_no_args(self):
        text = "tasks:\n  build:\n    cmd: echo hi\n"
        result = extract_task_args(self._tree(text), "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        text = "tasks:\n  build:\n    args:\n      - name\n"
        result = extract_task_args(self._tree(text), "deploy")
        self.assertEqual(result, [])

    def test_empty_args_list(self):
        text = "tasks:\n  build:\n    args: []\n"
        result = extract_task_args(self._tree(text), "build")
        self.assertEqual(result, [])

    def test_broken_yaml_returns_list(self):
        text = "tasks:\n  build:\n    args:\n      - name\n      - ver"
        result = extract_task_args(parse_document(text), "build")
        self.assertIsInstance(result, list)

    def test_incomplete_yaml_unclosed_template_in_cmd(self):
        """Args are still found when cmd contains an unclosed {{ template."""
        text = "tasks:\n  build:\n    args:\n      - name\n      - version\n    cmd: echo {{ arg."
        result = extract_task_args(parse_document(text), "build")
        # The _tree_without_broken_template fallback should recover these
        self.assertEqual(sorted(result), ["name", "version"])

    def test_does_not_return_args_from_other_task(self):
        text = (
            "tasks:\n"
            "  build:\n    args:\n      - build_arg\n"
            "  test:\n    args:\n      - test_arg\n"
        )
        tree = self._tree(text)
        self.assertEqual(extract_task_args(tree, "build"), ["build_arg"])
        self.assertEqual(extract_task_args(tree, "test"), ["test_arg"])


# ---------------------------------------------------------------------------
# extract_task_inputs
# ---------------------------------------------------------------------------


class TestExtractTaskInputs(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_named_inputs_kv_format(self):
        text = (
            "tasks:\n  build:\n    inputs:\n"
            "      - source: src/main.c\n"
            "      - header: include/defs.h\n"
        )
        result = extract_task_inputs(self._tree(text), "build")
        self.assertEqual(result, ["header", "source"])

    def test_skip_anonymous_inputs(self):
        text = (
            "tasks:\n  build:\n    inputs:\n"
            "      - src/main.c\n"
            "      - include/defs.h\n"
        )
        result = extract_task_inputs(self._tree(text), "build")
        self.assertEqual(result, [])

    def test_mixed_named_and_anonymous(self):
        text = (
            "tasks:\n  build:\n    inputs:\n"
            "      - src/main.c\n"
            "      - source: src/lib.c\n"
            "      - include/defs.h\n"
            "      - header: include/lib.h\n"
        )
        result = extract_task_inputs(self._tree(text), "build")
        self.assertEqual(result, ["header", "source"])

    def test_no_inputs_section(self):
        text = "tasks:\n  build:\n    cmd: echo hello\n"
        result = extract_task_inputs(self._tree(text), "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        text = "tasks:\n  build:\n    inputs:\n      - source: src/main.c\n"
        result = extract_task_inputs(self._tree(text), "deploy")
        self.assertEqual(result, [])

    def test_does_not_return_inputs_from_other_task(self):
        text = (
            "tasks:\n"
            "  build:\n    inputs:\n      - source: src/main.c\n"
            "  test:\n    inputs:\n      - fixture: tests/data.json\n"
        )
        tree = self._tree(text)
        self.assertEqual(extract_task_inputs(tree, "build"), ["source"])
        self.assertEqual(extract_task_inputs(tree, "test"), ["fixture"])

    def test_broken_yaml_returns_list(self):
        text = "tasks:\n  build:\n    inputs:\n      - source: src/main.c\n      - hea"
        result = extract_task_inputs(parse_document(text), "build")
        self.assertIsInstance(result, list)

    def test_incomplete_yaml_unclosed_template_in_cmd_inputs(self):
        """Named inputs are still found when cmd contains an unclosed {{ template."""
        text = (
            "tasks:\n  build:\n    inputs:\n"
            "      - source: src/main.c\n"
            "      - header: include/defs.h\n"
            "    cmd: echo {{ self.inputs."
        )
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["header", "source"])


# ---------------------------------------------------------------------------
# extract_task_outputs
# ---------------------------------------------------------------------------


class TestExtractTaskOutputs(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_named_outputs_kv_format(self):
        text = (
            "tasks:\n  build:\n    outputs:\n"
            "      - binary: dist/app\n"
            "      - log: logs/build.log\n"
        )
        result = extract_task_outputs(self._tree(text), "build")
        self.assertEqual(result, ["binary", "log"])

    def test_skip_anonymous_outputs(self):
        text = (
            "tasks:\n  build:\n    outputs:\n"
            "      - dist/app\n"
            "      - logs/build.log\n"
        )
        result = extract_task_outputs(self._tree(text), "build")
        self.assertEqual(result, [])

    def test_mixed_named_and_anonymous(self):
        text = (
            "tasks:\n  build:\n    outputs:\n"
            "      - dist/temp\n"
            "      - binary: dist/app\n"
            "      - logs/*.log\n"
            "      - report: reports/build.html\n"
        )
        result = extract_task_outputs(self._tree(text), "build")
        self.assertEqual(result, ["binary", "report"])

    def test_no_outputs_section(self):
        text = "tasks:\n  build:\n    cmd: echo hello\n"
        result = extract_task_outputs(self._tree(text), "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        text = "tasks:\n  build:\n    outputs:\n      - binary: dist/app\n"
        result = extract_task_outputs(self._tree(text), "deploy")
        self.assertEqual(result, [])

    def test_does_not_return_outputs_from_other_task(self):
        text = (
            "tasks:\n"
            "  build:\n    outputs:\n      - binary: dist/app\n"
            "  test:\n    outputs:\n      - report: test-report.html\n"
        )
        tree = self._tree(text)
        self.assertEqual(extract_task_outputs(tree, "build"), ["binary"])
        self.assertEqual(extract_task_outputs(tree, "test"), ["report"])

    def test_incomplete_yaml_unclosed_template_in_cmd_outputs(self):
        """Named outputs are still found when cmd contains an unclosed {{ template."""
        text = (
            "tasks:\n  build:\n    outputs:\n"
            "      - binary: dist/app\n"
            "      - log: logs/build.log\n"
            "    cmd: echo {{ self.outputs."
        )
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["binary", "log"])


# ---------------------------------------------------------------------------
# extract_task_names
# ---------------------------------------------------------------------------


class TestExtractTaskNames(unittest.TestCase):
    def _tree(self, text):
        return parse_document(text)

    def test_block_style_task_names(self):
        text = (
            "tasks:\n"
            "  compile:\n    cmd: gcc main.c\n"
            "  link:\n    cmd: ld main.o\n"
            "  build:\n    deps: [compile, link]\n"
        )
        result = extract_task_names(self._tree(text))
        self.assertEqual(result, ["build", "compile", "link"])

    def test_flow_style_task_names(self):
        text = "{ tasks: { task-1: { cmd: echo hi }, task-2: { cmd: echo bye } } }"
        result = extract_task_names(self._tree(text))
        self.assertIn("task-1", result)
        self.assertIn("task-2", result)

    def test_no_tasks_section(self):
        result = extract_task_names(self._tree("variables:\n  foo: bar\n"))
        self.assertEqual(result, [])

    def test_empty_document(self):
        result = extract_task_names(self._tree(""))
        self.assertEqual(result, [])

    def test_broken_yaml_partial_result(self):
        text = "tasks:\n  build:\n    cmd: gcc\n  test:\n    deps: ["
        result = extract_task_names(parse_document(text))
        self.assertIsInstance(result, list)

    def test_imported_task_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            imported = Path(tmpdir) / "utils.tasks"
            imported.write_text("tasks:\n  clean:\n    cmd: rm -rf build/\n")

            text = (
                "tasks:\n  build:\n    cmd: echo build\n"
                f"\nimports:\n  - file: utils.tasks\n    as: utils\n"
            )
            result = extract_task_names(parse_document(text), base_path=tmpdir)
            self.assertIn("build", result)
            self.assertIn("utils.clean", result)

    def test_missing_import_file_skipped(self):
        text = (
            "tasks:\n  build:\n    cmd: echo\n"
            "\nimports:\n  - file: nonexistent.tasks\n    as: ns\n"
        )
        result = extract_task_names(parse_document(text), base_path="/tmp")
        self.assertEqual(result, ["build"])

    def test_no_base_path_skips_imports(self):
        text = (
            "tasks:\n  build:\n    cmd: echo\n"
            "\nimports:\n  - file: utils.tasks\n    as: utils\n"
        )
        result = extract_task_names(parse_document(text), base_path=None)
        self.assertEqual(result, ["build"])

    def test_incomplete_yaml_unclosed_template_in_deps(self):
        """Task names are found even when a deps field has an unclosed {{ template."""
        text = "tasks:\n  build:\n    cmd: gcc main.c\n  test:\n    deps: [{{ tt."
        result = extract_task_names(parse_document(text))
        # At minimum 'build' should be recoverable via the fallback strategies
        self.assertIsInstance(result, list)
        self.assertIn("build", result)

    def test_incomplete_yaml_task_names_with_unclosed_bracket_in_deps(self):
        """Task names are found when the last task's deps list is unclosed."""
        text = "tasks:\n  compile:\n    cmd: gcc\n  build:\n    deps: ["
        result = extract_task_names(parse_document(text))
        self.assertIsInstance(result, list)
        # 'compile' should be findable; 'build' may or may not be recovered
        self.assertIn("compile", result)


if __name__ == "__main__":
    unittest.main()
