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
        init_handler = self.server.lsp._features["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result.capabilities.completion_provider)

        # Open document
        open_handler = self.server.lsp._features["textDocument/didOpen"]
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
        completion_handler = self.server.lsp._features["textDocument/completion"]
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
        open_handler = self.server.lsp._features["textDocument/didOpen"]
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
            TextDocumentContentChangeEvent,
        )

        change_handler = self.server.lsp._features["textDocument/didChange"]
        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/project/build.tt", version=2
            ),
            content_changes=[
                TextDocumentContentChangeEvent(
                    text="tasks:\n  test:\n    cmd: echo {{ tt.proj"
                )
            ],
        )
        change_handler(change_params)

        # Request completion
        completion_handler = self.server.lsp._features["textDocument/completion"]
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
        open_handler = self.server.lsp._features["textDocument/didOpen"]
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
        completion_handler = self.server.lsp._features["textDocument/completion"]
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
        init_handler = self.server.lsp._features["initialize"]
        init_params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )
        init_result = init_handler(init_params)
        self.assertIsNotNone(init_result)

        # Open and complete
        open_handler = self.server.lsp._features["textDocument/didOpen"]
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

        completion_handler = self.server.lsp._features["textDocument/completion"]
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
        shutdown_handler = self.server.lsp._features["shutdown"]
        shutdown_result = shutdown_handler()
        self.assertIsNone(shutdown_result)

        # Exit
        exit_handler = self.server.lsp._features["exit"]
        exit_result = exit_handler()
        self.assertIsNone(exit_result)

    def test_completion_in_variable_definition(self):
        """Test that completions work in variable definitions."""
        # Open document with variable using tt. in eval
        open_handler = self.server.lsp._features["textDocument/didOpen"]
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
        completion_handler = self.server.lsp._features["textDocument/completion"]
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(
                uri="file:///test/project/tasktree.yaml"
            ),
            position=Position(line=2, character=30),  # After "{{ tt.user"
        )
        result = completion_handler(completion_params)

        # Verify we get user_home and user_name
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"user_home", "user_name"})

    def test_completion_in_inputs_field(self):
        """Test that completions work in inputs field."""
        # Open document with inputs using tt.
        open_handler = self.server.lsp._features["textDocument/didOpen"]
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
        completion_handler = self.server.lsp._features["textDocument/completion"]
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


if __name__ == "__main__":
    unittest.main()
