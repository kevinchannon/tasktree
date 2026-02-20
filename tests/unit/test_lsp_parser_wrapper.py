"""Unit tests for LSP parser wrapper."""

import os
import unittest
import tempfile
from pathlib import Path

from tasktree.lsp.parser_wrapper import (
    parse_yaml_data,
    extract_variables,
    extract_task_args,
    extract_task_inputs,
    extract_task_outputs,
    get_env_var_names,
    extract_task_names,
    _extract_task_inputs_heuristic,
    _extract_task_outputs_heuristic,
    _extract_local_task_names_heuristic,
)


class TestParseYamlData(unittest.TestCase):
    """Test parse_yaml_data utility function."""

    def test_parse_valid_yaml(self):
        """Test parsing valid YAML returns dict."""
        text = "tasks:\n  build:\n    cmd: echo hello\n"
        result = parse_yaml_data(text)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("tasks", result)

    def test_parse_invalid_yaml_returns_none(self):
        """Test parsing invalid YAML returns None."""
        text = "invalid: yaml: content\n  - malformed\n"
        result = parse_yaml_data(text)
        self.assertIsNone(result)

    def test_parse_empty_document_returns_none(self):
        """Test parsing empty document returns None (yaml.safe_load returns None)."""
        result = parse_yaml_data("")
        self.assertIsNone(result)

    def test_parse_non_dict_returns_none(self):
        """Test parsing non-dict YAML (e.g. a list) returns None."""
        result = parse_yaml_data("- item1\n- item2\n")
        self.assertIsNone(result)

    def test_parse_complete_tasktree_yaml(self):
        """Test parsing complete tasktree YAML returns full data."""
        text = """
variables:
  foo: bar
tasks:
  build:
    cmd: echo hello
"""
        result = parse_yaml_data(text)
        self.assertIsNotNone(result)
        self.assertIn("variables", result)
        self.assertIn("tasks", result)


class TestExtractVariablesWithPreParsedData(unittest.TestCase):
    """Test extract_variables with pre-parsed data parameter."""

    def test_extract_with_pre_parsed_data(self):
        """Test that extract_variables works with pre-parsed data."""
        text = "variables:\n  foo: bar\n  baz: qux\n"
        data = parse_yaml_data(text)
        result = extract_variables(text, data=data)
        self.assertEqual(sorted(result), ["baz", "foo"])

    def test_extract_with_none_data_parses_text(self):
        """Test that extract_variables parses text when data is None."""
        text = "variables:\n  foo: bar\n"
        result = extract_variables(text, data=None)
        self.assertEqual(result, ["foo"])

    def test_extract_with_empty_data_returns_empty(self):
        """Test that extract_variables returns empty when data has no variables."""
        data = {"tasks": {"build": {"cmd": "echo hello"}}}
        result = extract_variables("", data=data)
        self.assertEqual(result, [])


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
        # PATH is virtually always set
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
        result = extract_variables(text)
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
        result = extract_variables(text)
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
        result = extract_variables(text)
        self.assertEqual(result, [])

    def test_empty_variables_section(self):
        """Test extracting from empty variables section."""
        text = """
variables: {}
"""
        result = extract_variables(text)
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
  - malformed
"""
        result = extract_variables(text)
        self.assertEqual(result, [])

    def test_empty_document(self):
        """Test handling empty document."""
        text = ""
        result = extract_variables(text)
        self.assertEqual(result, [])

    def test_variables_not_dict(self):
        """Test handling when variables is not a dict."""
        text = """
variables:
  - not
  - a
  - dict
"""
        result = extract_variables(text)
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
        result = extract_task_args(text, "build")
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
        result = extract_task_args(text, "build")
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
        result = extract_task_args(text, "build")
        self.assertEqual(sorted(result), ["build_type", "name", "version"])

    def test_no_args_in_task(self):
        """Test task with no args section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_task_args(text, "build")
        self.assertEqual(result, [])

    def test_empty_args_list(self):
        """Test task with empty args list."""
        text = """
tasks:
  build:
    args: []
"""
        result = extract_task_args(text, "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        """Test extracting args for non-existent task."""
        text = """
tasks:
  build:
    args:
      - name
"""
        result = extract_task_args(text, "deploy")
        self.assertEqual(result, [])

    def test_no_tasks_section(self):
        """Test extracting from YAML with no tasks section."""
        text = """
variables:
  foo: bar
"""
        result = extract_task_args(text, "build")
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
"""
        result = extract_task_args(text, "build")
        self.assertEqual(result, [])

    def test_args_not_list(self):
        """Test handling when args is not a list."""
        text = """
tasks:
  build:
    args: not-a-list
"""
        result = extract_task_args(text, "build")
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
        result = extract_task_inputs(text, "build")
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
        result = extract_task_inputs(text, "build")
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
        result = extract_task_inputs(text, "build")
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
        result = extract_task_inputs(text, "build")
        self.assertEqual(sorted(result), ["header", "source"])

    def test_no_inputs_in_task(self):
        """Test task with no inputs section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_task_inputs(text, "build")
        self.assertEqual(result, [])

    def test_empty_inputs_list(self):
        """Test task with empty inputs list."""
        text = """
tasks:
  build:
    inputs: []
"""
        result = extract_task_inputs(text, "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        """Test extracting inputs for non-existent task."""
        text = """
tasks:
  build:
    inputs:
      - source: src/main.c
"""
        result = extract_task_inputs(text, "deploy")
        self.assertEqual(result, [])

    def test_no_tasks_section(self):
        """Test extracting from YAML with no tasks section."""
        text = """
variables:
  foo: bar
"""
        result = extract_task_inputs(text, "build")
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
"""
        result = extract_task_inputs(text, "build")
        self.assertEqual(result, [])

    def test_inputs_not_list(self):
        """Test handling when inputs is not a list."""
        text = """
tasks:
  build:
    inputs: not-a-list
"""
        result = extract_task_inputs(text, "build")
        self.assertEqual(result, [])


class TestExtractTaskInputsHeuristic(unittest.TestCase):
    """Tests for _extract_task_inputs_heuristic function (incomplete YAML fallback)."""

    def test_extract_block_style_kv_inputs(self):
        """Test extracting named inputs in block key-value format from incomplete YAML."""
        text = """tasks:
  build:
    inputs:
      - source: src/main.c
      - hea"""  # Incomplete YAML
        result = _extract_task_inputs_heuristic(text, "build")
        self.assertIn("source", result)

    def test_extract_block_style_dict_inputs(self):
        """Test extracting named inputs in block dict format from incomplete YAML."""
        text = """tasks:
  build:
    inputs:
      - { source: src/main.c }
      - { header: inc"""  # Incomplete YAML
        result = _extract_task_inputs_heuristic(text, "build")
        self.assertIn("source", result)
        self.assertIn("header", result)

    def test_extract_flow_style_inputs(self):
        """Test extracting named inputs in flow style from incomplete YAML."""
        text = """tasks:
  build:
    inputs: [{ source: src/main.c }, { header: """  # Incomplete YAML
        result = _extract_task_inputs_heuristic(text, "build")
        self.assertIn("source", result)
        self.assertIn("header", result)

    def test_task_not_found(self):
        """Test that empty list is returned when task is not found."""
        text = """tasks:
  build:
    inputs:
      - source: src/main.c"""
        result = _extract_task_inputs_heuristic(text, "nonexistent")
        self.assertEqual(result, [])

    def test_no_inputs_field(self):
        """Test that empty list is returned when task has no inputs field."""
        text = """tasks:
  build:
    cmd: gcc"""
        result = _extract_task_inputs_heuristic(text, "build")
        self.assertEqual(result, [])

    def test_mixed_named_and_anonymous_inputs(self):
        """Test that only named inputs are extracted, anonymous are skipped."""
        text = """tasks:
  build:
    inputs:
      - src/file1.txt
      - source: src/main.c
      - include/"""
        result = _extract_task_inputs_heuristic(text, "build")
        self.assertIn("source", result)
        # Anonymous inputs should not appear
        self.assertNotIn("src/file1.txt", result)
        self.assertNotIn("include/", result)

    def test_fallback_on_incomplete_yaml(self):
        """Test that extract_task_inputs falls back to heuristic on incomplete YAML."""
        # This YAML is incomplete (missing closing quotes)
        text = """tasks:
  build:
    inputs:
      - source: "src/main.c
      - header: "include/de"""
        result = extract_task_inputs(text, "build")
        # Should use heuristic fallback and still find named inputs
        self.assertIn("source", result)
        self.assertIn("header", result)


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
        result = extract_task_outputs(text, "build")
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
        result = extract_task_outputs(text, "build")
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
        result = extract_task_outputs(text, "build")
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
        result = extract_task_outputs(text, "build")
        self.assertEqual(sorted(result), ["binary", "report"])

    def test_no_outputs_in_task(self):
        """Test task with no outputs section."""
        text = """
tasks:
  build:
    cmd: echo hello
"""
        result = extract_task_outputs(text, "build")
        self.assertEqual(result, [])

    def test_empty_outputs_list(self):
        """Test task with empty outputs list."""
        text = """
tasks:
  build:
    outputs: []
"""
        result = extract_task_outputs(text, "build")
        self.assertEqual(result, [])

    def test_task_not_found(self):
        """Test extracting outputs for non-existent task."""
        text = """
tasks:
  build:
    outputs:
      - binary: dist/app
"""
        result = extract_task_outputs(text, "deploy")
        self.assertEqual(result, [])

    def test_no_tasks_section(self):
        """Test extracting from YAML with no tasks section."""
        text = """
variables:
  foo: bar
"""
        result = extract_task_outputs(text, "build")
        self.assertEqual(result, [])

    def test_invalid_yaml(self):
        """Test graceful handling of invalid YAML."""
        text = """
invalid: yaml: content
"""
        result = extract_task_outputs(text, "build")
        self.assertEqual(result, [])

    def test_outputs_not_list(self):
        """Test handling when outputs is not a list."""
        text = """
tasks:
  build:
    outputs: not-a-list
"""
        result = extract_task_outputs(text, "build")
        self.assertEqual(result, [])


class TestExtractTaskOutputsHeuristic(unittest.TestCase):
    """Tests for _extract_task_outputs_heuristic function (incomplete YAML fallback)."""

    def test_extract_block_style_kv_outputs(self):
        """Test extracting named outputs in block key-value format from incomplete YAML."""
        text = """tasks:
  build:
    outputs:
      - binary: dist/app
      - lo"""  # Incomplete YAML
        result = _extract_task_outputs_heuristic(text, "build")
        self.assertIn("binary", result)

    def test_extract_block_style_dict_outputs(self):
        """Test extracting named outputs in block dict format from incomplete YAML."""
        text = """tasks:
  build:
    outputs:
      - { binary: dist/app }
      - { log: logs/bu"""  # Incomplete YAML
        result = _extract_task_outputs_heuristic(text, "build")
        self.assertIn("binary", result)
        self.assertIn("log", result)

    def test_extract_flow_style_outputs(self):
        """Test extracting named outputs in flow style from incomplete YAML."""
        text = """tasks:
  build:
    outputs: [{ binary: dist/app }, { log: """  # Incomplete YAML
        result = _extract_task_outputs_heuristic(text, "build")
        self.assertIn("binary", result)
        self.assertIn("log", result)

    def test_task_not_found(self):
        """Test that empty list is returned when task is not found."""
        text = """tasks:
  build:
    outputs:
      - binary: dist/app"""
        result = _extract_task_outputs_heuristic(text, "nonexistent")
        self.assertEqual(result, [])

    def test_no_outputs_field(self):
        """Test that empty list is returned when task has no outputs field."""
        text = """tasks:
  build:
    cmd: gcc"""
        result = _extract_task_outputs_heuristic(text, "build")
        self.assertEqual(result, [])

    def test_mixed_named_and_anonymous_outputs(self):
        """Test that only named outputs are extracted, anonymous are skipped."""
        text = """tasks:
  build:
    outputs:
      - dist/file1.txt
      - binary: dist/app
      - logs/"""
        result = _extract_task_outputs_heuristic(text, "build")
        self.assertIn("binary", result)
        # Anonymous outputs should not appear
        self.assertNotIn("dist/file1.txt", result)
        self.assertNotIn("logs/", result)

    def test_fallback_on_incomplete_yaml(self):
        """Test that extract_task_outputs falls back to heuristic on incomplete YAML."""
        # This YAML is incomplete (missing closing quotes)
        text = """tasks:
  build:
    outputs:
      - binary: "dist/app
      - log: "logs/bu"""
        result = extract_task_outputs(text, "build")
        # Should use heuristic fallback and still find named outputs
        self.assertIn("binary", result)
        self.assertIn("log", result)


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
        result = extract_task_names(text)
        self.assertEqual(result, ["build", "deploy", "test"])

    def test_extract_task_names_empty_tasks(self):
        """Test extracting task names when tasks section is empty."""
        text = "tasks: {}\n"
        result = extract_task_names(text)
        self.assertEqual(result, [])

    def test_extract_task_names_no_tasks_section(self):
        """Test extracting task names when no tasks section exists."""
        text = "variables:\n  foo: bar\n"
        result = extract_task_names(text)
        self.assertEqual(result, [])

    def test_extract_task_names_invalid_yaml_falls_back_to_heuristic(self):
        """Test that invalid YAML falls back to heuristic extraction."""
        # Incomplete YAML with an unclosed string
        text = "tasks:\n  build:\n    cmd: echo 'hello\n  test:\n    cmd: echo test\n"
        result = extract_task_names(text)
        # Heuristic should find at least the task names
        self.assertIn("build", result)
        self.assertIn("test", result)

    def test_extract_task_names_with_preparsed_data(self):
        """Test that pre-parsed data is used instead of re-parsing."""
        text = "tasks:\n  build:\n    cmd: echo build\n"
        data = parse_yaml_data(text)
        result = extract_task_names(text, data=data)
        self.assertEqual(result, ["build"])

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
        result = extract_task_names(text)
        self.assertEqual(result, ["alpha", "middle", "zebra"])

    def test_extract_task_names_with_imports(self):
        """Test extracting task names including from imported files."""
        # Create a temporary directory with an imported tasks file
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write the imported tasks file
            imported_file = Path(tmpdir) / "utils.tasks"
            imported_file.write_text(
                "tasks:\n  util_task:\n    cmd: echo util\n  helper:\n    cmd: echo help\n"
            )

            # Main file references the import
            text = f"""tasks:
  main_task:
    cmd: echo main
imports:
  - file: utils.tasks
    as: utils
"""
            result = extract_task_names(text, base_path=tmpdir)
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
        result = extract_task_names(text, base_path=None)
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
            result = extract_task_names(text, base_path=tmpdir)
            # Should only return local tasks; the missing import is silently skipped
            self.assertEqual(result, ["local_task"])


class TestExtractLocalTaskNamesHeuristic(unittest.TestCase):
    """Tests for _extract_local_task_names_heuristic function."""

    def test_extracts_task_names_from_standard_yaml(self):
        """Test extracting task names from standard YAML format."""
        text = "tasks:\n  build:\n    cmd: echo\n  test:\n    cmd: pytest\n"
        result = _extract_local_task_names_heuristic(text)
        self.assertIn("build", result)
        self.assertIn("test", result)

    def test_filters_known_field_names(self):
        """Test that known field names are not included as task names."""
        text = "tasks:\n  build:\n    cmd: echo\n    deps: []\n    args: []\n"
        result = _extract_local_task_names_heuristic(text)
        self.assertIn("build", result)
        self.assertNotIn("cmd", result)
        self.assertNotIn("deps", result)
        self.assertNotIn("args", result)

    def test_returns_empty_for_no_tasks_section(self):
        """Test returns empty list when there is no tasks section."""
        text = "variables:\n  foo: bar\n"
        result = _extract_local_task_names_heuristic(text)
        self.assertEqual(result, [])

    def test_returns_empty_for_4_space_indented_tasks(self):
        """Test that tasks with 4-space indentation are not detected (known limitation).

        The heuristic regex requires exactly 2-space indentation. Files using
        4-space (or any other) indentation will produce no results from this
        fallback.  The primary parser (yaml.safe_load) handles such files
        correctly; the heuristic is only invoked for incomplete/invalid YAML.
        """
        text = "tasks:\n    build:\n        cmd: echo\n    test:\n        cmd: pytest\n"
        result = _extract_local_task_names_heuristic(text)
        # 4-space indentation is not handled by the heuristic
        self.assertEqual(result, [])

    def test_returns_empty_for_flow_style_yaml(self):
        """Test that flow-style YAML task definitions are not detected (known limitation).

        In a flow-style file the structure may be a single line such as:
            tasks: {build: {cmd: echo build}, test: {cmd: pytest}}
        The line-by-line regex heuristic cannot parse this format.  The
        primary parser (yaml.safe_load) handles flow-style files correctly;
        the heuristic is only used when yaml.safe_load fails.
        """
        text = "tasks: {build: {cmd: echo build}, test: {cmd: pytest}}"
        result = _extract_local_task_names_heuristic(text)
        # Flow-style YAML is not handled by this heuristic
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
