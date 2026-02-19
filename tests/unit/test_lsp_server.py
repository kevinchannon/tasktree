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
            position=Position(line=2, character=len("    cmd: echo {{ tt.")),
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
            position=Position(line=2, character=len("    cmd: echo {{ tt.")),
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
            position=Position(line=2, character=len("    cmd: echo {{ tt.time")),
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
            position=Position(line=2, character=len("    deps: [buil")),
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
            position=Position(line=2, character=len("    cmd: echo {{ tt.user_name }} tt.")),
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
            position=Position(line=2, character=len("    cmd: echo {{ tt.proj")),
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
            position=Position(line=5, character=len("    cmd: echo {{ var.")),
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
            position=Position(line=6, character=len("    cmd: echo {{ var.foo")),
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
            position=Position(line=2, character=len("    cmd: echo {{ var.")),
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
            position=Position(line=8, character=len("    cmd: echo {{ var.")),
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
            position=Position(line=5, character=len("    cmd: echo {{ var.my_")),
        )

        result = completion_handler(completion_params)

        # Should get both my_* variables
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"my_var", "my_other"})

    def test_completion_multiple_templates_on_line(self):
        """Test completion with multiple templates on the same line."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open document with multiple templates on one line
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="variables:\n  foo: bar\n  baz: qux\ntasks:\n  test:\n    cmd: echo {{ var.foo }} and {{ var.",
            )
        )
        open_handler(open_params)

        # Request completion at the second {{ var. on the same line
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=len("    cmd: echo {{ var.foo }} and {{ var.")),
        )

        result = completion_handler(completion_params)

        # Should get all variables (not affected by the first completed template)
        self.assertEqual(len(result.items), 2)
        var_names = {item.label for item in result.items}
        self.assertEqual(var_names, {"baz", "foo"})

    def test_completion_arg_in_cmd_field(self):
        """Test that completion returns arg.* variables when in cmd field."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with task args
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    args:\n      - name\n      - version\n    cmd: echo {{ arg.",
            )
        )
        open_handler(open_params)

        # Request completion in cmd field after "{{ arg."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=len("    cmd: echo {{ arg.")),
        )

        result = completion_handler(completion_params)

        # Verify we get both args
        self.assertEqual(len(result.items), 2)
        arg_names = {item.label for item in result.items}
        self.assertEqual(arg_names, {"name", "version"})

    def test_completion_arg_not_in_cmd_field(self):
        """Test that arg.* completion IS provided in deps field (for parameterized deps)."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with task args
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    args:\n      - name\n    deps: {{ arg.",
            )
        )
        open_handler(open_params)

        # Request completion in deps field (parameterized dependencies support arg.*)
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=4, character=len("    deps: {{ arg.")),
        )

        result = completion_handler(completion_params)

        # Should get arg completion (arg.* is valid in deps fields for parameterized dependencies)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "name")

    def test_completion_arg_dict_format(self):
        """Test arg.* completion with dict-format args (with types/defaults)."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with dict-format args
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text='tasks:\n  build:\n    args:\n      - build_type:\n          choices: ["debug", "release"]\n      - target:\n          type: str\n    cmd: echo {{ arg.',
            )
        )
        open_handler(open_params)

        # Request completion in cmd field
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=7, character=len("    cmd: echo {{ arg.")),
        )

        result = completion_handler(completion_params)

        # Verify we get both args
        self.assertEqual(len(result.items), 2)
        arg_names = {item.label for item in result.items}
        self.assertEqual(arg_names, {"build_type", "target"})

    def test_completion_arg_filtered_by_prefix(self):
        """Test that arg.* completion filters by prefix."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with args
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    args:\n      - build_type\n      - build_dir\n      - target\n    cmd: echo {{ arg.build",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ arg.build"
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=6, character=len("    cmd: echo {{ arg.build")),
        )

        result = completion_handler(completion_params)

        # Verify we only get build_* args
        self.assertEqual(len(result.items), 2)
        arg_names = {item.label for item in result.items}
        self.assertEqual(arg_names, {"build_type", "build_dir"})

    def test_completion_arg_no_args_defined(self):
        """Test that arg.* returns empty when task has no args."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with task but no args
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ arg.",
            )
        )
        open_handler(open_params)

        # Request completion
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=len("    cmd: echo {{ arg.")),
        )

        result = completion_handler(completion_params)

        # Should get no completions
        self.assertEqual(len(result.items), 0)

    def test_completion_arg_different_tasks(self):
        """Test that arg.* completion is scoped to the current task."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with multiple tasks with different args
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    args:\n      - build_type\n    cmd: echo building\n  deploy:\n    args:\n      - environment\n    cmd: echo {{ arg.",
            )
        )
        open_handler(open_params)

        # Request completion in deploy task's cmd
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=8, character=len("    cmd: echo {{ arg.")),
        )

        result = completion_handler(completion_params)

        # Should only get deploy task's args (not build task's args)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "environment")

    def test_completion_self_inputs_in_cmd_field(self):
        """Test self.inputs.* completion in cmd field."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with named inputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - source: src/main.c\n      - header: include/defs.h\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.inputs."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=len("    cmd: echo {{ self.inputs.")),
        )

        result = completion_handler(completion_params)

        # Should get both named inputs
        self.assertEqual(len(result.items), 2)
        input_names = {item.label for item in result.items}
        self.assertEqual(input_names, {"header", "source"})

    def test_completion_self_inputs_not_in_cmd_field(self):
        """Test that self.inputs.* completion works in deps fields."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document where we're in deps field (not cmd)
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - source: src/main.c\n    deps: [{{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion in deps field
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=4, character=len("    deps: [{{ self.inputs.")),
        )

        result = completion_handler(completion_params)

        # Should get completions (self.inputs.* works in deps fields too)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "source")

    def test_completion_self_inputs_filtered_by_prefix(self):
        """Test that self.inputs.* completion filters by prefix."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with multiple named inputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - source: src/main.c\n      - header: include/defs.h\n      - config: config.yaml\n    cmd: echo {{ self.inputs.so",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.inputs.so"
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=6, character=len("    cmd: echo {{ self.inputs.so")),
        )

        result = completion_handler(completion_params)

        # Should only get "source" (starts with "so")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "source")

    def test_completion_self_inputs_skip_anonymous(self):
        """Test that self.inputs.* completion skips anonymous inputs."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with only anonymous inputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - src/main.c\n      - include/defs.h\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.inputs."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=len("    cmd: echo {{ self.inputs.")),
        )

        result = completion_handler(completion_params)

        # Should get no completions (only anonymous inputs)
        self.assertEqual(len(result.items), 0)

    def test_completion_self_inputs_mixed_named_anonymous(self):
        """Test self.inputs.* completion with mixed named and anonymous inputs."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with mixed named and anonymous inputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - src/main.c\n      - source: src/lib.c\n      - include/defs.h\n      - header: include/lib.h\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.inputs."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=7, character=len("    cmd: echo {{ self.inputs.")),
        )

        result = completion_handler(completion_params)

        # Should only get named inputs
        self.assertEqual(len(result.items), 2)
        input_names = {item.label for item in result.items}
        self.assertEqual(input_names, {"header", "source"})

    def test_completion_self_inputs_different_tasks(self):
        """Test that self.inputs.* completion is scoped to the current task."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with multiple tasks with different inputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    inputs:\n      - source: src/main.c\n    cmd: echo building\n  deploy:\n    inputs:\n      - config: deploy.yaml\n    cmd: echo {{ self.inputs.",
            )
        )
        open_handler(open_params)

        # Request completion in deploy task's cmd
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=8, character=len("    cmd: echo {{ self.inputs.")),
        )

        result = completion_handler(completion_params)

        # Should only get deploy task's inputs (not build task's inputs)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "config")

    def test_completion_self_outputs_in_cmd_field(self):
        """Test self.outputs.* completion in cmd field."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with named outputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - binary: dist/app\n      - log: logs/build.log\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.outputs."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=len("    cmd: echo {{ self.outputs.")),
        )

        result = completion_handler(completion_params)

        # Should get both named outputs
        self.assertEqual(len(result.items), 2)
        output_names = {item.label for item in result.items}
        self.assertEqual(output_names, {"binary", "log"})

    def test_completion_self_outputs_not_in_cmd_field(self):
        """Test that self.outputs.* completion works in deps fields."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document where we're in deps field (not cmd)
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - binary: dist/app\n    deps: [{{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion in deps field
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=4, character=len("    deps: [{{ self.outputs.")),
        )

        result = completion_handler(completion_params)

        # Should get completions (self.outputs.* works in deps fields too)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "binary")

    def test_completion_self_outputs_filtered_by_prefix(self):
        """Test that self.outputs.* completion filters by prefix."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with multiple named outputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - binary: dist/app\n      - log: logs/build.log\n      - report: reports/build.html\n    cmd: echo {{ self.outputs.lo",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.outputs.lo"
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=6, character=len("    cmd: echo {{ self.outputs.lo")),
        )

        result = completion_handler(completion_params)

        # Should only get "log" (starts with "lo")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "log")

    def test_completion_self_outputs_skip_anonymous(self):
        """Test that self.outputs.* completion skips anonymous outputs."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with only anonymous outputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - dist/app\n      - logs/build.log\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.outputs."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=5, character=len("    cmd: echo {{ self.outputs.")),
        )

        result = completion_handler(completion_params)

        # Should get no completions (only anonymous outputs)
        self.assertEqual(len(result.items), 0)

    def test_completion_self_outputs_mixed_named_anonymous(self):
        """Test self.outputs.* completion with mixed named and anonymous outputs."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with mixed named and anonymous outputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - dist/temp\n      - binary: dist/app\n      - logs/*.log\n      - report: reports/build.html\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion after "{{ self.outputs."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=7, character=len("    cmd: echo {{ self.outputs.")),
        )

        result = completion_handler(completion_params)

        # Should only get named outputs
        self.assertEqual(len(result.items), 2)
        output_names = {item.label for item in result.items}
        self.assertEqual(output_names, {"binary", "report"})

    def test_completion_self_outputs_different_tasks(self):
        """Test that self.outputs.* completion is scoped to the current task."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with multiple tasks with different outputs
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    outputs:\n      - binary: dist/app\n    cmd: echo building\n  deploy:\n    outputs:\n      - log: deploy.log\n    cmd: echo {{ self.outputs.",
            )
        )
        open_handler(open_params)

        # Request completion in deploy task's cmd
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=8, character=len("    cmd: echo {{ self.outputs.")),
        )

        result = completion_handler(completion_params)

        # Should only get deploy task's outputs (not build task's outputs)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].label, "log")


    def test_completion_env_returns_env_vars(self):
        """Test that env.* completion returns environment variable names."""
        import os
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with env. prefix in cmd
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ env.",
            )
        )
        open_handler(open_params)

        # Request completion at "{{ env."
        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=len("    cmd: echo {{ env.")),
        )

        result = completion_handler(completion_params)

        # Should return env var names (PATH is virtually always set)
        self.assertIsInstance(result.items, list)
        var_names = {item.label for item in result.items}
        self.assertIn("PATH", var_names)
        # Should contain all env vars
        self.assertEqual(var_names, set(os.environ.keys()))

    def test_completion_env_sorted_alphabetically(self):
        """Test that env.* completion items are in alphabetical order."""
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ env.",
            )
        )
        open_handler(open_params)

        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=len("    cmd: echo {{ env.")),
        )

        result = completion_handler(completion_params)

        labels = [item.label for item in result.items]
        self.assertEqual(labels, sorted(labels))

    def test_completion_env_filtered_by_prefix(self):
        """Test that env.* completion filters by partial prefix."""
        import os
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open document with partial env var name (PATH)
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    cmd: echo {{ env.PATH",
            )
        )
        open_handler(open_params)

        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=len("    cmd: echo {{ env.PATH")),
        )

        result = completion_handler(completion_params)

        # All returned items should start with "PATH"
        for item in result.items:
            self.assertTrue(
                item.label.startswith("PATH"),
                f"Expected label starting with 'PATH', got '{item.label}'"
            )
        # PATH itself should be present (it's always set)
        var_names = {item.label for item in result.items}
        self.assertIn("PATH", var_names)

    def test_completion_env_no_scoping_outside_cmd(self):
        """Test that env.* completion works even outside cmd fields (no scoping)."""
        import os
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open a document with env. outside of cmd (in working_dir)
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text="tasks:\n  build:\n    working_dir: {{ env.",
            )
        )
        open_handler(open_params)

        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=len("    working_dir: {{ env.")),
        )

        result = completion_handler(completion_params)

        # Should still return env vars (no scoping restriction)
        var_names = {item.label for item in result.items}
        self.assertIn("PATH", var_names)

    def test_completion_env_at_top_level(self):
        """Test that env.* completion works at top level (variables section)."""
        import os
        server = create_server()
        open_handler = server.handlers["textDocument/didOpen"]
        completion_handler = server.handlers["textDocument/completion"]

        # Open document with env. in variables section
        open_params = DidOpenTextDocumentParams(
            text_document=TextDocumentItem(
                uri="file:///test/tasktree.yaml",
                language_id="yaml",
                version=1,
                text='variables:\n  my_var:\n    eval: "echo {{ env.',
            )
        )
        open_handler(open_params)

        completion_params = CompletionParams(
            text_document=TextDocumentIdentifier(uri="file:///test/tasktree.yaml"),
            position=Position(line=2, character=len('    eval: "echo {{ env.')),
        )

        result = completion_handler(completion_params)

        # Should return env vars even in variables section
        var_names = {item.label for item in result.items}
        self.assertIn("PATH", var_names)


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
