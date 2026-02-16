"""Tests for LSP server module."""

import unittest
from unittest.mock import MagicMock, patch

import tasktree
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

    @patch("tasktree.lsp.server.main")
    def test_main_execution_path(self, mock_main):
        """Test that __name__ == '__main__' execution path calls main()."""
        # Import and execute the module's __main__ block
        import runpy

        mock_main.reset_mock()
        runpy.run_module("tasktree.lsp.server", run_name="__main__")
        mock_main.assert_called_once()


if __name__ == "__main__":
    unittest.main()
