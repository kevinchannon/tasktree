"""Tests for LSP server module."""

import unittest
from unittest.mock import MagicMock, patch

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
        server = TasktreeLanguageServer("tasktree-lsp", "v0.1")
        self.assertEqual(server.name, "tasktree-lsp")

    @patch("tasktree.lsp.server.TasktreeLanguageServer")
    def test_main_starts_server(self, mock_server_class):
        """Test that main() creates and starts the server."""
        mock_server = MagicMock()
        mock_server_class.return_value = mock_server

        main()

        mock_server_class.assert_called_once_with("tasktree-lsp", "v0.1")
        mock_server.start_io.assert_called_once()


if __name__ == "__main__":
    unittest.main()
