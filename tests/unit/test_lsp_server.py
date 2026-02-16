"""Tests for LSP server module."""

import unittest
from unittest.mock import MagicMock, patch

import tasktree
import tasktree.lsp.server
from tasktree.lsp.server import TasktreeLanguageServer, create_server, main
from lsprotocol.types import (
    InitializeParams,
    CompletionOptions,
    TextDocumentSyncKind,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    TextDocumentItem,
    VersionedTextDocumentIdentifier,
    TextDocumentContentChangeEvent,
    CompletionParams,
    TextDocumentIdentifier,
    Position,
    CompletionList,
)


class TestTasktreeLanguageServer(unittest.TestCase):
    """Tests for TasktreeLanguageServer class."""

    def test_server_instantiation(self):
        """Test that the LSP server can be instantiated."""
        server = TasktreeLanguageServer("test-server", "v0.1")
        self.assertIsNotNone(server)
        self.assertEqual(server.name, "test-server")
        self.assertEqual(server.version, "v0.1")


class TestCreateServer(unittest.TestCase):
    """Tests for create_server function."""

    def test_create_server_returns_language_server(self):
        """Test that create_server returns a TasktreeLanguageServer instance."""
        server = create_server()
        self.assertIsInstance(server, TasktreeLanguageServer)
        self.assertEqual(server.name, "tasktree-lsp")
        self.assertEqual(server.version, tasktree.__version__)

    def test_initialize_handler_registered(self):
        """Test that the initialize handler is registered."""
        server = create_server()
        # Verify that the server has an initialize handler registered
        self.assertIn("initialize", server.handlers)

    def test_initialize_returns_capabilities(self):
        """Test that initialize handler returns server capabilities."""
        server = create_server()
        params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )

        # Get the initialize handler and call it
        handler = server.handlers["initialize"]
        result = handler(params)

        # Verify the result contains text sync capability
        self.assertIsNotNone(result.capabilities)
        self.assertEqual(result.capabilities.text_document_sync, TextDocumentSyncKind.Full)

        # Verify the result contains completion capabilities
        self.assertIsNotNone(result.capabilities.completion_provider)
        self.assertIsInstance(result.capabilities.completion_provider, CompletionOptions)
        self.assertEqual(result.capabilities.completion_provider.trigger_characters, ["."])

    def test_shutdown_handler_registered(self):
        """Test that the shutdown handler is registered."""
        server = create_server()
        self.assertIn("shutdown", server.handlers)

    def test_exit_handler_registered(self):
        """Test that the exit handler is registered."""
        server = create_server()
        self.assertIn("exit", server.handlers)

    def test_shutdown_handler_callable(self):
        """Test that the shutdown handler can be called."""
        server = create_server()
        handler = server.handlers["shutdown"]
        # Should not raise an exception
        result = handler()
        self.assertIsNone(result)

    def test_exit_handler_callable(self):
        """Test that the exit handler can be called."""
        server = create_server()
        handler = server.handlers["exit"]
        # Should not raise an exception
        result = handler()
        self.assertIsNone(result)

    def test_did_open_handler_registered(self):
        """Test that the did_open handler is registered."""
        server = create_server()
        self.assertIn("textDocument/didOpen", server.handlers)

    def test_did_open_stores_document(self):
        """Test that did_open stores document contents."""
        server = create_server()
        handler = server.handlers["textDocument/didOpen"]

        # Create a document open notification
        params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo hello",
            )
        )

        # Call the handler
        handler(params)

        # Verify the document was stored
        self.assertIn("file:///test/tasktree.yaml", server.documents)
        self.assertEqual(
            server.documents["file:///test/tasktree.yaml"],
            "tasks:\n  hello:\n    cmd: echo hello",
        )

    def test_did_change_handler_registered(self):
        """Test that the did_change handler is registered."""
        server = create_server()
        self.assertIn("textDocument/didChange", server.handlers)

    def test_did_change_updates_document(self):
        """Test that did_change updates document contents."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        change_handler = server.handlers["textDocument/didChange"]

        # First open a document
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo hello",
            )
        )
        open_handler(open_params)

        # Now change it
        # In lsprotocol 2025.0.0+, for full sync mode we use a simple object with text attribute
        class ChangeEvent:
            def __init__(self, text):
                self.text = text

        change_params = DidChangeTextDocumentParams(
            text_document=VersionedTextDocumentIdentifier(
                uri="file:///test/tasktree.yaml", version=2
            ),
            content_changes=[ChangeEvent(text="tasks:\n  hello:\n    cmd: echo world")],
        )
        change_handler(change_params)

        # Verify the document was updated
        self.assertEqual(
            server.documents["file:///test/tasktree.yaml"],
            "tasks:\n  hello:\n    cmd: echo world",
        )

    def test_completion_handler_registered(self):
        """Test that the completion handler is registered."""
        server = create_server()
        self.assertIn("textDocument/completion", server.handlers)

    def test_completion_returns_list(self):
        """Test that completion handler returns a CompletionList."""
        server = create_server()
        handler = server.handlers["textDocument/completion"]

        # Create a completion request
        params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=25),
        )

        # Call the handler
        result = handler(params)

        # Verify we get a CompletionList
        self.assertIsInstance(result, CompletionList)
        self.assertFalse(result.is_incomplete)
        self.assertIsInstance(result.items, list)

    def test_completion_tt_builtin_variables(self):
        """Test that completion returns tt.* built-in variables."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with a cmd field
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo {{ tt.",
            )
        )
        open_handler(open_params)

        # Request completion at the end of "{{ tt."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=25),  # After "{{ tt."
        )

        result = completion_handler(completion_params)

        # Verify we get all 8 built-in variables
        self.assertEqual(len(result.items), 8)
        var_names = {item.label for item in result.items}
        expected_vars = {
            "project_root",
            "recipe_dir",
            "task_name",
            "working_dir",
            "timestamp",
            "timestamp_unix",
            "user_home",
            "user_name",
        }
        self.assertEqual(var_names, expected_vars)

    def test_completion_tt_filtered_by_prefix(self):
        """Test that completion filters tt.* variables by prefix."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with a partial variable name
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo {{ tt.time",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ tt.time"
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=29),  # After "{{ tt.time"
        )

        result = completion_handler(completion_params)

        # Verify we only get timestamp variables
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"timestamp", "timestamp_unix"})

    def test_completion_not_in_cmd_field(self):
        """Test that completion returns empty when not in cmd field."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document where we're not in a cmd field
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    deps: [build]",
            )
        )
        open_handler(open_params)

        # Request completion in deps field
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=15),
        )

        result = completion_handler(completion_params)

        # Verify we get no completions
        self.assertEqual(len(result.items), 0)

    def test_completion_outside_template_braces(self):
        """Test no completion when cursor is after closing }}."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open document with completed template followed by tt.
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo {{ tt.user_name }} tt.",
            )
        )
        open_handler(open_params)

        # Request completion after the second "tt." (outside template)
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=42),  # After "}} tt."
        )
        result = completion_handler(completion_params)

        # Should get no completions (cursor is outside {{ }})
        self.assertEqual(len(result.items), 0)

    def test_completion_with_trailing_braces(self):
        """Test completion strips trailing }} from partial match."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open document and insert cursor in middle of variable with closing braces
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo {{ tt.proj }}",
            )
        )
        open_handler(open_params)

        # Request completion at "proj" (before closing }})
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=24),  # After "proj", before }}
        )
        result = completion_handler(completion_params)

        # Should get project_root completion
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "project_root")

    def test_completion_var_user_variables(self):
        """Test that completion returns var.* user-defined variables."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with variables defined
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="variables:\n  foo: bar\n  baz: qux\ntasks:\n  hello:\n    cmd: echo {{ var.",
            )
        )
        open_handler(open_params)

        # Request completion at the end of "{{ var."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=26),  # After "{{ var."
        )

        result = completion_handler(completion_params)

        # Verify we get both user variables
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"foo", "baz"})

    def test_completion_var_filtered_by_prefix(self):
        """Test that completion filters var.* variables by prefix."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with variables
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="variables:\n  foo: bar\n  foobar: baz\n  qux: test\ntasks:\n  hello:\n    cmd: echo {{ var.foo",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ var.foo"
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=6, character=29),  # After "{{ var.foo"
        )

        result = completion_handler(completion_params)

        # Verify we only get foo-prefixed variables
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"foo", "foobar"})

    def test_completion_var_no_variables_defined(self):
        """Test that completion returns empty when no variables are defined."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with no variables section
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  hello:\n    cmd: echo {{ var.",
            )
        )
        open_handler(open_params)

        # Request completion at the end of "{{ var."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=26),  # After "{{ var."
        )

        result = completion_handler(completion_params)

        # Verify we get no completions
        self.assertEqual(len(result.items), 0)

    def test_completion_var_complex_variables(self):
        """Test that completion works with complex variable specs (env, eval, read)."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with complex variable definitions
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text='variables:\n  simple: value\n  from_env:\n    env: HOME\n  from_eval:\n    eval: "echo test"\ntasks:\n  hello:\n    cmd: echo {{ var.',
            )
        )
        open_handler(open_params)

        # Request completion
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=8, character=26),  # After "{{ var."
        )

        result = completion_handler(completion_params)

        # Verify we get all three variable names
        self.assertEqual(len(result.items), 3)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"simple", "from_env", "from_eval"})

    def test_completion_var_with_trailing_braces(self):
        """Test completion with partial var name and trailing }} (common typo pattern)."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open document with partial variable name followed by }}
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="variables:\n  my_var: value\n  my_other: test\ntasks:\n  build:\n    cmd: echo {{ var.my_}}",
            )
        )
        open_handler(open_params)

        # Request completion at "my_" (before closing }})
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=24),  # After "my_", before }}
        )

        result = completion_handler(completion_params)

        # Should get both my_* variables
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"my_var", "my_other"})


class TestMain(unittest.TestCase):
    """Tests for main entry point."""

    def test_main_server_name(self):
        """Test that the server name is set to 'tasktree-lsp'."""
        server = TasktreeLanguageServer("tasktree-lsp", tasktree.__version__)
        self.assertEqual(server.name, "tasktree-lsp")

    def test_main_server_version(self):
        """Test that the server version is set to tasktree.__version__."""
        server = TasktreeLanguageServer("tasktree-lsp", tasktree.__version__)
        self.assertEqual(server.version, tasktree.__version__)

    @patch("tasktree.lsp.server.create_server")
    def test_main_starts_server(self, mock_create_server):
        """Test that main() creates and starts the server."""
        mock_server = MagicMock()
        mock_create_server.return_value = mock_server

        main()

        mock_create_server.assert_called_once()
        mock_server.start_io.assert_called_once()

    def test_main_execution_path(self):
        """Test that the module has __main__ guard that would call main()."""
        import inspect

        # Read the source file and verify it has the __main__ guard
        source = inspect.getsource(tasktree.lsp.server)
        self.assertIn('if __name__ == "__main__":', source)
        self.assertIn("main()", source)


if __name__ == "__main__":
    unittest.main()
