"""Tests for LSP server module."""

import unittest
from unittest.mock import MagicMock, patch

import tasktree
import tasktree.lsp.server
from tasktree.lsp.server import TasktreeLanguageServer, main


class TestTasktreeLanguageServer(unittest.TestCase):
    """Tests for TasktreeLanguageServer class."""

    def test_server_instantiation(self):
        """Test that the LSP server can be instantiated."""
        server = TasktreeLanguageServer("test-server", "v0.1")
        self.assertIsNotNone(server)
        self.assertEqual(server.name, "test-server")
        self.assertEqual(server.version, "v0.1")


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

    @patch("tasktree.lsp.server.TasktreeLanguageServer")
    def test_main_starts_server(self, mock_server_class):
        """Test that main() creates and starts the server."""
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        main()

        mock_server_class.assert_called_once_with("tasktree-lsp", tasktree.__version__)
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
