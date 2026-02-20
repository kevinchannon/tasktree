"""Integration tests for LSP completion feature."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from lsprotocol.types import (
    InitializeParams,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    VersionedTextDocumentIdentifier,
    CompletionParams,
    TextDocumentItem,
    TextDocumentContentChangeEvent,
    TextDocumentIdentifier,
    Position,
)
from tasktree.lsp.server import create_server


class TestLSPCompletionIntegration(unittest.TestCase):
    """Integration tests for LSP completion using server instance."""

    def setUp(self):
        """Create a server instance for each test."""
        self.server = create_server()

    def test_full_workflow_tt_completion(self):
        """Test complete workflow: initialize -> open -> complete."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ tt.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=25),  # After "{{ tt."
        )
        result = completion_handler(completion_params)

        # Verify completions
        self.assertEqual(len(result.items), 8)
        var_names = {item.label for item in result.items}
        expected = {
            "project_root",
            "recipe_dir",
            "task_name",
            "working_dir",
            "timestamp",
            "timestamp_unix",
            "user_home",
            "user_name",
        }
        self.assertEqual(var_names, expected)

    def test_completion_after_document_change(self):
        """Test that completion works after document changes."""
        # Open document
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/build.tt",
                language_id="yaml",
                version=1,
                text="tasks:\n  test:\n    cmd: echo hello",
            )
        )
        open_handler(open_params)

        # Change document to add tt. prefix
        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                Mock(text="tasks:\n  test:\n    cmd: echo {{ tt.proj")
            ],
        )
        change_handler(change_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/project/build.tt"),
            position=Position(line=2, character=29),  # After "{{ tt.proj"
        )
        result = completion_handler(completion_params)

        # Verify we get only project_root
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "project_root")

    def test_completion_in_working_dir_field(self):
        """Test that completions work in working_dir and other fields."""
        # Open document
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    working_dir: {{ tt.proj",
            )
        )
        open_handler(open_params)

        # Request completion in working_dir field
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=31),  # After "{{ tt.proj"
        )
        result = completion_handler(completion_params)

        # Verify we get project_root completion
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "project_root")

    def test_server_lifecycle_with_completion(self):
        """Test full LSP lifecycle including completion."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result)

        # Open and complete
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_handler(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri="file:///test/task.tt",
                    language_id="yaml",
                    version=1,
                    text="tasks:\n  run:\n    cmd: {{ tt.user",
                )
            )
        )

        completion_handler = self.server.handlers["textDocument/completion"]
        result = completion_handler(
            CompletionParams(
                text_document=TextDocumentIdentifier(uri="file:///test/task.tt"),
                position=Position(line=2, character=20),
            )
        )

        # Should get user_home and user_name
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"user_home", "user_name"})

        # Shutdown
        shutdown_handler = self.server.handlers["shutdown"]
        shutdown_result = shutdown_handler()
        self.assertIsNone(shutdown_result)

        # Exit
        exit_handler = self.server.handlers["exit"]
        exit_result = exit_handler()
        self.assertIsNone(exit_result)

    def test_completion_in_variable_definition(self):
        """Test that completions work in variable definitions."""
        # Open document with variable using tt. in eval
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text='variables:\n  my_var:\n    eval: "echo {{ tt.user"',
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=26),  # After "{{ tt.user" (at 'r' in user)
        )
        result = completion_handler(completion_params)

        # Verify we get user_home and user_name
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"user_home", "user_name"})

    def test_completion_in_inputs_field(self):
        """Test that completions work in inputs field."""
        # Open document with inputs using tt.
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - {{ tt.recipe",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=3, character=22),  # After "{{ tt.recipe"
        )
        result = completion_handler(completion_params)

        # Verify we get recipe_dir
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "recipe_dir")

    def test_full_workflow_var_completion(self):
        """Test complete workflow for var.* user variable completion."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document with variables
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="variables:\n  my_var: value\n  another_var: test\ntasks:\n  build:\n    cmd: echo {{ var.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=5, character=26),  # After "{{ var."
        )
        result = completion_handler(completion_params)

        # Verify completions
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"my_var", "another_var"})

    def test_var_completion_after_document_change(self):
        """Test that var.* completion works after document changes."""
        # Open document with variables
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/build.tt",
                language_id="yaml",
                version=1,
                text="variables:\n  foo: bar\ntasks:\n  test:\n    cmd: echo hello",
            )
        )
        open_handler(open_params)

        # Change document to add var. prefix
        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                Mock(text="variables:\n  foo: bar\n  foobar: baz\ntasks:\n  test:\n    cmd: echo {{ var.foo")
            ],
        )
        change_handler(change_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/project/build.tt"),
            position=Position(line=5, character=29),  # After "{{ var.foo"
        )
        result = completion_handler(completion_params)

        # Verify we get only foo-prefixed variables
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"foo", "foobar"})

    def test_var_completion_with_complex_variables(self):
        """Test that var.* completion works with complex variable specs."""
        # Open document with env/eval/read variables
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text='variables:\n  simple: value\n  from_env:\n    env: HOME\n  from_eval:\n    eval: "echo test"\ntasks:\n  build:\n    cmd: echo {{ var.',
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=8, character=21),  # After "{{ var."
        )
        result = completion_handler(completion_params)

        # Verify we get all three variable names
        self.assertEqual(len(result.items), 3)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"simple", "from_env", "from_eval"})

    def test_var_completion_no_variables_section(self):
        """Test that var.* completion returns empty when no variables defined."""
        # Open document without variables section
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ var.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=26),  # After "{{ var."
        )
        result = completion_handler(completion_params)

        # Verify we get no completions
        self.assertEqual(len(result.items), 0)

    def test_full_workflow_self_inputs_completion(self):
        """Test complete workflow for self.inputs.* named input completion."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document with named inputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - source: src/main.c\n      - header: include/defs.h\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=5, character=len("    cmd: echo {{ self.inputs.")),
        )
        result = completion_handler(completion_params)

        # Verify completions
        self.assertEqual(len(result.items), 2)
        input_names = {item.label for item in result.items}
        self.assertEqual(input_names, {"header", "source"})

    def test_self_inputs_completion_after_document_change(self):
        """Test that self.inputs.* completion works after document changes."""
        # Open document with named inputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/build.tt",
                language_id="yaml",
                version=1,
                text="tasks:\n  test:\n    inputs:\n      - source: src/main.c\n    cmd: echo hello",
            )
        )
        open_handler(open_params)

        # Change document to add self.inputs. prefix and more inputs
        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                Mock(text="tasks:\n  test:\n    inputs:\n      - source: src/main.c\n      - header: include/defs.h\n    cmd: echo {{ self.inputs.")
            ],
        )
        change_handler(change_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/project/build.tt"),
            position=Position(line=5, character=len("    cmd: echo {{ self.inputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get both inputs
        self.assertEqual(len(result.items), 2)
        input_names = {item.label for item in result.items}
        self.assertEqual(input_names, {"header", "source"})

    def test_self_inputs_completion_skip_anonymous(self):
        """Test that self.inputs.* completion skips anonymous inputs."""
        # Open document with only anonymous inputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - src/main.c\n      - include/defs.h\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=5, character=len("    cmd: echo {{ self.inputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get no completions (only anonymous inputs)
        self.assertEqual(len(result.items), 0)

    def test_self_inputs_completion_mixed_named_anonymous(self):
        """Test self.inputs.* completion with mixed named and anonymous inputs."""
        # Open document with mixed inputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - src/main.c\n      - source: src/lib.c\n      - include/defs.h\n      - header: include/lib.h\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=7, character=len("    cmd: echo {{ self.inputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get only named inputs
        self.assertEqual(len(result.items), 2)
        input_names = {item.label for item in result.items}
        self.assertEqual(input_names, {"header", "source"})

    def test_self_inputs_completion_in_working_dir(self):
        """Test self.inputs.* completion works in working_dir field."""
        server = create_server()
        init_handler = server.handlers["initialize"]
        init_handler(InitializeParams(process_id=12345, root_uri="file:///test", capabilities={}))

        # Open a document with named inputs
        yaml_text = """tasks:
  build:
    inputs:
      - source: src/main.c
      - header: include/defs.h
    working_dir: {{ self.inputs."""

        open_handler = server.handlers["textDocument/didOpen"]
        open_handler(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri="file:///test.yaml",
                    language_id="yaml",
                    version=1,
                    text=yaml_text,
                )
            )
        )

        # Request completion in working_dir field
        completion_handler = server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.yaml"),
            position=Position(line=5, character=len("    working_dir: {{ self.inputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get named inputs in working_dir field
        self.assertEqual(len(result.items), 2)
        input_names = {item.label for item in result.items}
        self.assertEqual(input_names, {"header", "source"})

    def test_self_inputs_completion_in_arg_default(self):
        """Test self.inputs.* completion works in args default field."""
        server = create_server()
        init_handler = server.handlers["initialize"]
        init_handler(InitializeParams(process_id=12345, root_uri="file:///test", capabilities={}))

        # Open a document with named inputs and arg with default
        yaml_text = """tasks:
  build:
    inputs:
      - config: config/settings.yml
    args:
      - conf_path: { default: "{{ self.inputs." }"""

        open_handler = server.handlers["textDocument/didOpen"]
        open_handler(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri="file:///test.yaml",
                    language_id="yaml",
                    version=1,
                    text=yaml_text,
                )
            )
        )

        # Request completion in arg default field
        completion_handler = server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.yaml"),
            position=Position(line=5, character=len('      - conf_path: { default: "{{ self.inputs.')),
        )
        result = completion_handler(completion_params)

        # Verify we get named inputs in default field
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "config")

    def test_full_workflow_self_outputs_completion(self):
        """Test complete workflow for self.outputs.* named output completion."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document with named outputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - binary: dist/app\n      - log: logs/build.log\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=5, character=len("    cmd: echo {{ self.outputs.")),
        )
        result = completion_handler(completion_params)

        # Verify completions
        self.assertEqual(len(result.items), 2)
        output_names = {item.label for item in result.items}
        self.assertEqual(output_names, {"binary", "log"})

    def test_self_outputs_completion_after_document_change(self):
        """Test that self.outputs.* completion works after document changes."""
        # Open document with named outputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/build.tt",
                language_id="yaml",
                version=1,
                text="tasks:\n  test:\n    outputs:\n      - binary: dist/app\n    cmd: echo hello",
            )
        )
        open_handler(open_params)

        # Change document to add self.outputs. prefix and more outputs
        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                Mock(text="tasks:\n  test:\n    outputs:\n      - binary: dist/app\n      - log: logs/test.log\n    cmd: echo {{ self.outputs.")
            ],
        )
        change_handler(change_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/project/build.tt"),
            position=Position(line=5, character=len("    cmd: echo {{ self.outputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get both outputs
        self.assertEqual(len(result.items), 2)
        output_names = {item.label for item in result.items}
        self.assertEqual(output_names, {"binary", "log"})

    def test_self_outputs_completion_skip_anonymous(self):
        """Test that self.outputs.* completion skips anonymous outputs."""
        # Open document with only anonymous outputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - dist/app\n      - logs/build.log\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=5, character=len("    cmd: echo {{ self.outputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get no completions (only anonymous outputs)
        self.assertEqual(len(result.items), 0)

    def test_self_outputs_completion_mixed_named_anonymous(self):
        """Test self.outputs.* completion with mixed named and anonymous outputs."""
        # Open document with mixed outputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - dist/temp\n      - binary: dist/app\n      - logs/*.log\n      - report: reports/build.html\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=7, character=len("    cmd: echo {{ self.outputs.")),
        )
        result = completion_handler(completion_params)

        # Verify we get only named outputs
        self.assertEqual(len(result.items), 2)
        output_names = {item.label for item in result.items}
        self.assertEqual(output_names, {"binary", "report"})

    def test_arg_completion_in_working_dir(self):
        """Test arg.* completion works in working_dir field."""
        server = create_server()
        init_handler = server.handlers["initialize"]
        init_handler(InitializeParams(process_id=12345, root_uri="file:///test", capabilities={}))

        # Open a document with args
        yaml_text = """tasks:
  build:
    args:
      - build_dir
      - mode
    working_dir: {{ arg."""

        open_handler = server.handlers["textDocument/didOpen"]
        open_handler(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri="file:///test.yaml",
                    language_id="yaml",
                    version=1,
                    text=yaml_text,
                )
            )
        )

        # Request completion in working_dir field
        completion_handler = server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.yaml"),
            position=Position(line=5, character=len("    working_dir: {{ arg.")),
        )
        result = completion_handler(completion_params)

        # Verify we get args in working_dir field
        self.assertEqual(len(result.items), 2)
        arg_names = {item.label for item in result.items}
        self.assertEqual(arg_names, {"build_dir", "mode"})

    def test_arg_completion_in_outputs_field(self):
        """Test that arg.* completion works in outputs field."""
        # Open a document with a task that has args and outputs
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_handler(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri="file:///test.yaml",
                    language_id="yaml",
                    version=1,
                    text="""tasks:
  deploy:
    args:
      - app_name
      - version
    outputs: ["deploy-{{ arg.""",
                )
            )
        )

        # Request completion in outputs field after "{{ arg."
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.yaml"),
            position=Position(line=5, character=len('    outputs: ["deploy-{{ arg.')),
        )
        result = completion_handler(completion_params)

        # Verify we get args in outputs field
        self.assertEqual(len(result.items), 2)
        arg_names = {item.label for item in result.items}
        self.assertEqual(arg_names, {"app_name", "version"})

    def test_arg_completion_in_deps_field(self):
        """Test that arg.* completion works in deps field."""
        # Open a document with a task that has args and deps
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_handler(
            DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri="file:///test.yaml",
                    language_id="yaml",
                    version=1,
                    text="""tasks:
  consumer:
    args:
      - mode
      - target
    deps:
      - process: [{{ arg.""",
                )
            )
        )

        # Request completion in deps field after "{{ arg."
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.yaml"),
            position=Position(line=6, character=len("      - process: [{{ arg.")),
        )
        result = completion_handler(completion_params)

        # Verify we get args in deps field
        self.assertEqual(len(result.items), 2)
        arg_names = {item.label for item in result.items}
        self.assertEqual(arg_names, {"mode", "target"})


    def test_full_workflow_env_completion(self):
        """Test complete workflow for env.* environment variable completion."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ env.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=len("    cmd: echo {{ env.")),
        )
        result = completion_handler(completion_params)

        # Verify completions include all env vars
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, set(os.environ.keys()))
        # Results should be alphabetically sorted
        labels = [item.label for item in result.items]
        self.assertEqual(labels, sorted(labels))

    def test_env_completion_filtered_by_prefix(self):
        """Test that env.* completion filters by partial prefix."""
        # Open document with "PATH" partial prefix
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ env.PATH",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=len("    cmd: echo {{ env.PATH")),
        )
        result = completion_handler(completion_params)

        # All results should start with "PATH"
        for item in result.items:
            self.assertTrue(item.label.startswith("PATH"))

    def test_env_completion_no_scoping_in_various_fields(self):
        """Test that env.* completion works in all YAML fields (no scoping)."""
        # Open document with env. in variables section (not in a task)
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text='variables:\n  home:\n    eval: "echo {{ env.',
            )
        )
        open_handler(open_params)

        # Request completion in variables section
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=len('    eval: "echo {{ env.')),
        )
        result = completion_handler(completion_params)

        # Should return all env vars (no scoping restriction for env.*)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, set(os.environ.keys()))

    def test_env_completion_updates_after_document_change(self):
        """Test that env.* completion works correctly after document change."""
        # Open document (without env. prefix initially)
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/build.tt",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo hello",
            )
        )
        open_handler(open_params)

        # Change document to add env. prefix
        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                Mock(text="tasks:\n  build:\n    cmd: echo {{ env.PATH")
            ],
        )
        change_handler(change_params)

        # Request completion
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/project/build.tt"),
            position=Position(line=2, character=len("    cmd: echo {{ env.PATH")),
        )
        result = completion_handler(completion_params)

        # All results should start with "PATH" (filtered by prefix)
        for item in result.items:
            self.assertTrue(item.label.startswith("PATH"))


class TestDepsTaskNameCompletionIntegration(unittest.TestCase):
    """Integration tests for task name completion in deps fields."""

    def setUp(self):
        self.server = create_server()

    def test_full_workflow_deps_task_name_completion(self):
        """Test complete workflow: initialize -> open -> complete task names in deps."""
        # Initialize
        init_handler = self.server.handlers["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document with multiple tasks
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasktree.yaml",
                language_id="yaml",
                version=1,
                text=(
                    "tasks:\n"
                    "  compile:\n"
                    "    cmd: gcc main.c\n"
                    "  link:\n"
                    "    cmd: ld main.o\n"
                    "  build:\n"
                    "    deps:\n"
                    "      - "
                ),
            )
        )
        open_handler(open_params)

        # Request completion at the deps list item
        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=7, character=len("      - ")),
        )
        result = completion_handler(completion_params)

        labels = {item.label for item in result.items}
        self.assertIn("compile", labels)
        self.assertIn("link", labels)
        # Current task 'build' should NOT appear
        self.assertNotIn("build", labels)

    def test_deps_completions_update_after_document_change(self):
        """Test that deps completions reflect task list changes after document edit."""
        open_handler = self.server.handlers["textDocument/didOpen"]
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/project/tasks.tt",
                language_id="yaml",
                version=1,
                text=(
                    "tasks:\n"
                    "  build:\n"
                    "    cmd: echo build\n"
                    "  test:\n"
                    "    deps:\n"
                    "      - "
                ),
            )
        )
        open_handler(open_params)

        # Add a new task via document change
        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/tasks.tt", version=2
            ),
            content_changes=[
                TextDocumentContentChangeEvent(
                    text=(
                        "tasks:\n"
                        "  build:\n"
                        "    cmd: echo build\n"
                        "  package:\n"
                        "    cmd: echo package\n"
                        "  test:\n"
                        "    deps:\n"
                        "      - "
                    )
                )
            ],
        )
        change_handler(change_params)

        completion_handler = self.server.handlers["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/project/tasks.tt"),
            position=Position(line=7, character=len("      - ")),
        )
        result = completion_handler(completion_params)

        labels = {item.label for item in result.items}
        # Newly added task should appear
        self.assertIn("package", labels)

    def test_deps_with_imported_tasks(self):
        """Test that imported task names appear with namespace prefix in deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write the imported tasks file
            imported = Path(tmpdir) / "utils.tasks"
            imported.write_text(
                "tasks:\n  clean:\n    cmd: rm -rf build/\n"
            )

            doc_uri = f"file://{tmpdir}/main.tt"
            text = (
                "tasks:\n"
                "  build:\n"
                "    cmd: echo build\n"
                "  test:\n"
                "    deps:\n"
                "      - "
                f"\nimports:\n  - file: utils.tasks\n    as: utils\n"
            )
            open_handler = self.server.handlers["textDocument/didOpen"]
            open_handler(DidOpenTextDocumentParams(
                text_document=TextDocumentItem(
                    uri=doc_uri, language_id="yaml", version=1, text=text,
                )
            ))

            completion_handler = self.server.handlers["textDocument/completion"]
            result = completion_handler(CompletionParams(
                text_document=TextDocumentIdentifier(uri=doc_uri),
                position=Position(line=5, character=len("      - ")),
            ))

            labels = {item.label for item in result.items}
            # Local task should appear
            self.assertIn("build", labels)
            # Imported task should appear with namespace prefix
            self.assertIn("utils.clean", labels)


if __name__ == "__main__":
    unittest.main()
