"""Tests for LSP server module."""

import unittest
from unittest.mock import MagicMock, patch

import tasktree
import tasktree.lsp.server
from tasktree.lsp.server import TasktreeLanguageServer, create_server, main
from pygls.lsp.types import InitializeParams, CompletionOptions


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
        self.assertIn("initialize", server.lsp._features)

    def test_initialize_returns_capabilities(self):
        """Test that initialize handler returns server capabilities."""
        server = create_server()
        params = InitializeParams(
            process_id=12345, root_uri="file:///test/project", capabilities={}
        )

        # Get the initialize handler and call it
        handler = server.lsp._features["initialize"]
        result = handler(params)

        # Verify the result contains completion capabilities
        self.assertIsNotNone(result.capabilities)
        self.assertIsNotNone(result.capabilities.completion_provider)
        self.assertIsInstance(result.capabilities.completion_provider, CompletionOptions)
        self.assertEqual(result.capabilities.completion_provider.trigger_characters, ["."])


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
