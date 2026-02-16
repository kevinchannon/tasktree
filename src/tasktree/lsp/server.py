"""Tasktree LSP server main entry point."""

from pygls.lsp.server import LanguageServer


class TasktreeLanguageServer(LanguageServer):
    """Language server for tasktree files."""

    pass


def main() -> None:
    """Start the tasktree LSP server."""
    server = TasktreeLanguageServer("tasktree-lsp", "v0.1")
    server.start_io()


if __name__ == "__main__":
    main()
