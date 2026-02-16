"""Integration tests for LSP completion feature."""

import unittest
from lsprotocol.types import (
    InitializeParams,
    DidOpenTextDocumentParams,
    CompletionParams,
    TextDocumentItem,
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
        from lsprotocol.types import (
            DidChangeTextDocumentParams,
            VersionedTextDocumentIdentifier,
        )

        # In lsprotocol 2025.0.0+, for full sync mode we use a simple object with text attribute
        class ChangeEvent:
            def __init__(self, text):
                self.text = text

        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                ChangeEvent(text="tasks:\n  test:\n    cmd: echo {{ tt.proj")
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
        from lsprotocol.types import (
            DidChangeTextDocumentParams,
            VersionedTextDocumentIdentifier,
        )

        class ChangeEvent:
            def __init__(self, text):
                self.text = text

        change_handler = self.server.handlers["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                ChangeEvent(
                    text="variables:\n  foo: bar\n  foobar: baz\ntasks:\n  test:\n    cmd: echo {{ var.foo"
                )
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


if __name__ == "__main__":
    unittest.main()
