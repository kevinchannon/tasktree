"""Tasktree LSP server main entry point."""

from pygls.lsp.server import LanguageServer

import tasktree


class TasktreeLanguageServer(LanguageServer):
    """Language server for tasktree files."""

    pass


def main() -> None:
    """Start the tasktree LSP server."""
    server = TasktreeLanguageServer("tasktree-lsp", tasktree.__version__)
    server.start_io()


if __name__ == "__main__":
    main()
