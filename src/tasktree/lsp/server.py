"""Tasktree LSP server main entry point."""

from pygls.lsp.server import LanguageServer
from pygls.lsp.types import (
    InitializeParams,
    InitializeResult,
    ServerCapabilities,
    CompletionOptions,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    CompletionParams,
    CompletionList,
)

import tasktree

__all__ = ["TasktreeLanguageServer", "main"]


class TasktreeLanguageServer(LanguageServer):
    """Language server for tasktree files.

    Phase 0 Implementation (Basic Structure):
    - Server initialization and I/O handling
    - Basic LSP protocol support via pygls

    Planned Capabilities (Future Phases):
    - Syntax validation for tasktree.yaml and tt.yaml files
    - Auto-completion for task names, dependencies, and built-in variables
    - Hover documentation for task definitions and variables
    - Go-to-definition for task references
    - Diagnostic messages for configuration errors
    - Code actions for common refactoring operations
    """

    def __init__(self, name: str, version: str):
        """Initialize the language server."""
        super().__init__(name, version)
        # Store document contents in memory
        self.documents: dict[str, str] = {}


def create_server() -> TasktreeLanguageServer:
    """Create and configure the tasktree LSP server."""
    server = TasktreeLanguageServer("tasktree-lsp", tasktree.__version__)

    @server.feature("initialize")
    def initialize(params: InitializeParams) -> InitializeResult:
        """Handle LSP initialize request."""
        return InitializeResult(
            capabilities=ServerCapabilities(
                completion_provider=CompletionOptions(
                    trigger_characters=["."],
                )
            )
        )

    @server.feature("shutdown")
    def shutdown() -> None:
        """Handle LSP shutdown request."""
        pass

    @server.feature("exit")
    def exit() -> None:
        """Handle LSP exit notification."""
        pass

    @server.feature("textDocument/didOpen")
    def did_open(params: DidOpenTextDocumentParams) -> None:
        """Handle document open notification."""
        uri = params.text_document.uri
        text = params.text_document.text
        server.documents[uri] = text

    @server.feature("textDocument/didChange")
    def did_change(params: DidChangeTextDocumentParams) -> None:
        """Handle document change notification."""
        uri = params.text_document.uri
        # In full sync mode, we get the entire document in the first change
        if params.content_changes:
            server.documents[uri] = params.content_changes[0].text

    @server.feature("textDocument/completion")
    def completion(params: CompletionParams) -> CompletionList:
        """Handle completion request."""
        # Return empty list for now - will implement completion logic in next commit
        return CompletionList(is_incomplete=False, items=[])

    return server


def main() -> None:
    """Start the tasktree LSP server."""
    server = create_server()
    server.start_io()


if __name__ == "__main__":
    main()
