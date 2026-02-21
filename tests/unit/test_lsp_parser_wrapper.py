"""Unit tests for LSP parser wrapper.

Updated for the tree-sitter refactor (Phase 6): functions now accept a
Tree object instead of raw text or (text, data) pairs.

Removed classes (superseded by test_ts_context.py coverage):
- TestParseYamlData        — parse_yaml_data() was removed
- TestExtractVariablesWithPreParsedData — data= parameter was removed
- TestExtractTaskInputsHeuristic  — heuristic replaced by tree-sitter
- TestExtractTaskOutputsHeuristic — heuristic replaced by tree-sitter
- TestExtractLocalTaskNamesHeuristic — heuristic replaced by tree-sitter
"""

import os
import unittest
import tempfile
from pathlib import Path

from tasktree.lsp.parser_wrapper import (
    extract_variables,
    extract_task_args,
    extract_task_inputs,
    extract_task_outputs,
    get_env_var_names,
    extract_task_names,
)
from tasktree.lsp.ts_context import parse_document


class TestGetEnvVarNames(unittest.TestCase):
    """Test get_env_var_names function."""

    def test_returns_list(self):
        """Test that get_env_var_names returns a list."""
        result = get_env_var_names()
        self.assertIsInstance(result, list)

    def test_returns_sorted_list(self):
        """Test that the returned list is alphabetically sorted."""
        result = get_env_var_names()
        self.assertEqual(result, sorted(result))

    def test_includes_known_env_vars(self):
        """Test that known environment variables are included."""
        result = get_env_var_names()
        self.assertIn("PATH", result)

    def test_reflects_current_environment(self):
        """Test that the list reflects os.environ."""
        result = get_env_var_names()
        self.assertEqual(set(result), set(os.environ.keys()))

    def test_custom_env_var_included(self):
        """Test that a newly set environment variable appears in results."""
        test_var = "TASKTREE_LSP_TEST_VAR_12345"
        os.environ[test_var] = "test_value"
        try:
            result = get_env_var_names()
            self.assertIn(test_var, result)
        finally:
            del os.environ[test_var]


class TestExtractVariables(unittest.TestCase):
    """Test variable extraction from YAML."""

    def test_extract_simple_variables(self):
        """Test extracting simple string variables."""
        text = """
variables:
  foo: bar
  baz: qux
"""
        result = extract_variables(parse_document(text))
        self.assertEqual(sorted(result), ["baz", "foo"])

    def test_extract_complex_variables(self):
        """Test extracting variables with env/eval/read specs."""
        text = """
variables:
  simple: value
  from_env:
    env: HOME
    default: /tmp
  from_eval:
    eval: "echo hello"
  from_file:
    read: path/to/file
"""
        result = extract_variables(parse_document(text))
        self.assertEqual(
            sorted(result), ["from_env", "from_eval", "from_file", "simple"]
        )

    def test_no_variables_section(self):
        """Test extracting from YAML with no variables section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_variables(parse_document(text))
        self.assertEqual(result, [])

    def test_empty_variables_section(self):
        """Test extracting from empty variables section."""
        text = """
variables: {}
"""
        result = extract_variables(parse_document(text))
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
  - malformed
"""
        result = extract_variables(parse_document(text))
        self.assertEqual(result, [])

    def test_empty_document(self):
        """Test handling empty document."""
        result = extract_variables(parse_document(""))
        self.assertEqual(result, [])

    def test_variables_not_dict(self):
        """Test handling when variables is not a dict."""
        text = """
variables:
  - not
  - a
  - dict
"""
        result = extract_variables(parse_document(text))
        self.assertEqual(result, [])


class TestExtractTaskArgs(unittest.TestCase):
    """Test task argument extraction from YAML."""

    def test_extract_args_dict_format(self):
        """Test extracting args in dict format (with type/default/etc)."""
        text = """
tasks:
  build:
    args:
      - build_type:
          choices: ["debug", "release"]
          default: "debug"
      - target:
          type: str
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(sorted(result), ["build_type", "target"])

    def test_extract_args_string_format(self):
        """Test extracting args in simple string format."""
        text = """
tasks:
  build:
    args:
      - name
      - version
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(sorted(result), ["name", "version"])

    def test_extract_args_mixed_format(self):
        """Test extracting args with mixed string and dict format."""
        text = """
tasks:
  build:
    args:
      - name
      - build_type:
          default: "debug"
      - version
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(sorted(result), ["build_type", "name", "version"])

    def test_no_args_in_task(self):
        """Test task with no args section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_empty_args_list(self):
        """Test task with empty args list."""
        text = """
tasks:
  build:
    args: []
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        """Test extracting args for non-existent task."""
        text = """
tasks:
  build:
    args:
      - name
"""
        result = extract_task_args(parse_document(text), "deploy")
        self.assertEqual(result, [])

    def test_no_tasks_section(self):
        """Test extracting from YAML with no tasks section."""
        text = """
variables:
  foo: bar
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_args_not_list(self):
        """Test handling when args is not a list."""
        text = """
tasks:
  build:
    args: not-a-list
"""
        result = extract_task_args(parse_document(text), "build")
        self.assertEqual(result, [])


class TestExtractTaskInputs(unittest.TestCase):
    """Test task input extraction from YAML."""

    def test_extract_named_inputs_key_value_format(self):
        """Test extracting named inputs in key-value format."""
        text = """
tasks:
  build:
    inputs:
      - source: src/main.c
      - header: include/defs.h
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["header", "source"])

    def test_extract_named_inputs_dict_format(self):
        """Test extracting named inputs in dict format."""
        text = """
tasks:
  build:
    inputs:
      - name: src/main.c
      - config: config.yaml
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["config", "name"])

    def test_skip_anonymous_inputs(self):
        """Test that anonymous inputs are not extracted."""
        text = """
tasks:
  build:
    inputs:
      - src/main.c
      - include/defs.h
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_mixed_named_and_anonymous_inputs(self):
        """Test extracting only named inputs from mixed format."""
        text = """
tasks:
  build:
    inputs:
      - src/main.c
      - source: src/lib.c
      - include/defs.h
      - header: include/lib.h
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["header", "source"])

    def test_no_inputs_in_task(self):
        """Test task with no inputs section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_empty_inputs_list(self):
        """Test task with empty inputs list."""
        text = """
tasks:
  build:
    inputs: []
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        """Test extracting inputs for non-existent task."""
        text = """
tasks:
  build:
    inputs:
      - source: src/main.c
"""
        result = extract_task_inputs(parse_document(text), "deploy")
        self.assertEqual(result, [])

    def test_no_tasks_section(self):
        """Test extracting from YAML with no tasks section."""
        text = """
variables:
  foo: bar
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_inputs_not_list(self):
        """Test handling when inputs is not a list."""
        text = """
tasks:
  build:
    inputs: not-a-list
"""
        result = extract_task_inputs(parse_document(text), "build")
        self.assertEqual(result, [])


class TestExtractTaskOutputs(unittest.TestCase):
    """Test task output extraction from YAML."""

    def test_extract_named_outputs_key_value_format(self):
        """Test extracting named outputs in key-value format."""
        text = """
tasks:
  build:
    outputs:
      - binary: dist/app
      - log: logs/build.log
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["binary", "log"])

    def test_extract_named_outputs_dict_format(self):
        """Test extracting named outputs in dict format."""
        text = """
tasks:
  build:
    outputs:
      - executable: dist/app.exe
      - debug_symbols: dist/app.pdb
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["debug_symbols", "executable"])

    def test_skip_anonymous_outputs(self):
        """Test that anonymous outputs are not extracted."""
        text = """
tasks:
  build:
    outputs:
      - dist/app
      - dist/lib.so
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_mixed_named_and_anonymous_outputs(self):
        """Test extracting only named outputs from mixed format."""
        text = """
tasks:
  build:
    outputs:
      - dist/temp.txt
      - binary: dist/app
      - logs/*.log
      - report: reports/build.html
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(sorted(result), ["binary", "report"])

    def test_no_outputs_in_task(self):
        """Test task with no outputs section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_empty_outputs_list(self):
        """Test task with empty outputs list."""
        text = """
tasks:
  build:
    outputs: []
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        """Test extracting outputs for non-existent task."""
        text = """
tasks:
  build:
    outputs:
      - binary: dist/app
"""
        result = extract_task_outputs(parse_document(text), "deploy")
        self.assertEqual(result, [])

    def test_no_tasks_section(self):
        """Test extracting from YAML with no tasks section."""
        text = """
variables:
  foo: bar
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(result, [])

    def test_outputs_not_list(self):
        """Test handling when outputs is not a list."""
        text = """
tasks:
  build:
    outputs: not-a-list
"""
        result = extract_task_outputs(parse_document(text), "build")
        self.assertEqual(result, [])


class TestExtractTaskNames(unittest.TestCase):
    """Tests for extract_task_names function."""

    def test_extract_task_names_from_valid_yaml(self):
        """Test extracting task names from valid YAML."""
        text = """tasks:
  build:
    cmd: echo build
  test:
    cmd: echo test
  deploy:
    cmd: echo deploy
"""
        result = extract_task_names(parse_document(text))
        self.assertEqual(result, ["build", "deploy", "test"])

    def test_extract_task_names_empty_tasks(self):
        """Test extracting task names when tasks section is empty."""
        text = "tasks: {}\n"
        result = extract_task_names(parse_document(text))
        self.assertEqual(result, [])

    def test_extract_task_names_no_tasks_section(self):
        """Test extracting task names when no tasks section exists."""
        text = "variables:\n  foo: bar\n"
        result = extract_task_names(parse_document(text))
        self.assertEqual(result, [])

    def test_extract_task_names_sorted_alphabetically(self):
        """Test that task names are returned in sorted order."""
        text = """tasks:
  zebra:
    cmd: echo z
  alpha:
    cmd: echo a
  middle:
    cmd: echo m
"""
        result = extract_task_names(parse_document(text))
        self.assertEqual(result, ["alpha", "middle", "zebra"])

    def test_extract_task_names_with_imports(self):
        """Test extracting task names including from imported files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            imported_file = Path(tmpdir) / "utils.tasks"
            imported_file.write_text(
                "tasks:\n  util_task:\n    cmd: echo util\n  helper:\n    cmd: echo help\n"
            )

            text = f"""tasks:
  main_task:
    cmd: echo main
imports:
  - file: utils.tasks
    as: utils
"""
            result = extract_task_names(parse_document(text), base_path=tmpdir)
            self.assertIn("main_task", result)
            self.assertIn("utils.util_task", result)
            self.assertIn("utils.helper", result)

    def test_extract_task_names_without_base_path_skips_imports(self):
        """Test that imports are not followed when base_path is None."""
        text = """tasks:
  main_task:
    cmd: echo main
imports:
  - file: utils.tasks
    as: utils
"""
        result = extract_task_names(parse_document(text), base_path=None)
        self.assertEqual(result, ["main_task"])

    def test_extract_task_names_missing_import_file_is_skipped(self):
        """Test that missing import files are silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            text = """tasks:
  local_task:
    cmd: echo local
imports:
  - file: nonexistent.tasks
    as: missing
"""
            result = extract_task_names(parse_document(text), base_path=tmpdir)
            self.assertEqual(result, ["local_task"])

    def test_extract_task_names_import_without_namespace_is_skipped(self):
        """Test that import entries without an 'as:' namespace are silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            imported_file = Path(tmpdir) / "utils.tasks"
            imported_file.write_text("tasks:\n  util_task:\n    cmd: echo util\n")

            text = f"""tasks:
  main_task:
    cmd: echo main
imports:
  - file: utils.tasks
"""
            result = extract_task_names(parse_document(text), base_path=tmpdir)
            self.assertEqual(result, ["main_task"])


if __name__ == "__main__":
    unittest.main()
