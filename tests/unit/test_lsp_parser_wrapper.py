"""Unit tests for LSP parser wrapper."""

import unittest
from tasktree.lsp.parser_wrapper import (
    extract_variables,
    extract_task_args,
    extract_task_inputs,
    _extract_task_inputs_heuristic,
)


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


if __name__ == "__main__":
    unittest.main()
