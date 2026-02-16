"""Tasktree LSP server main entry point."""

from pygls.lsp.server import LanguageServer
from lsprotocol.types import (
    InitializeParams,
    InitializeResult,
    ServerCapabilities,
    CompletionOptions,
    TextDocumentSyncKind,
    DidOpenTextDocumentParams,
    DidChangeTextDocumentParams,
    CompletionParams,
    CompletionList,
    CompletionItem,
    CompletionItemKind,
)

import tasktree
from tasktree.lsp.builtin_variables import BUILTIN_VARIABLES
from tasktree.lsp.position_utils import get_prefix_at_position
from tasktree.lsp.parser_wrapper import extract_variables

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
        # Store handler references for testing
        self.handlers: dict[str, callable] = {}


def create_server() -> TasktreeLanguageServer:
    """Create and configure the tasktree LSP server."""
    server = TasktreeLanguageServer("tasktree-lsp", tasktree.__version__)

    @server.feature("initialize")
    def initialize(params: InitializeParams) -> InitializeResult:
        """Handle LSP initialize request.

        Args:
            params: Client initialization parameters including process ID, root URI, and capabilities

        Returns:
            InitializeResult with server capabilities including text document sync
            (full mode) and completion provider with '.' as trigger character
        """
        return InitializeResult(
            capabilities=ServerCapabilities(
                text_document_sync=TextDocumentSyncKind.Full,
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
        """Handle document open notification.

        Stores the document text in memory for later processing.

        Args:
            params: Document open parameters containing URI and initial text content
        """
        uri = params.text_document.uri
        text = params.text_document.text
        server.documents[uri] = text

    @server.feature("textDocument/didChange")
    def did_change(params: DidChangeTextDocumentParams) -> None:
        """Handle document change notification.

        Updates the stored document text when changes occur. Operates in
        full sync mode where the entire document content is sent.

        Args:
            params: Document change parameters containing URI and content changes
        """
        uri = params.text_document.uri
        # In full sync mode, we get the entire document in the first change
        if params.content_changes:
            server.documents[uri] = params.content_changes[0].text

    @server.feature("textDocument/completion")
    def completion(params: CompletionParams) -> CompletionList:
        """Handle completion request.

        Provides context-aware completions for tasktree YAML files.
        Currently supports:
        - tt.* built-in variable completion
        - var.* user-defined variable completion

        Args:
            params: Completion request parameters containing document URI and cursor position

        Returns:
            CompletionList containing matching completion items, or empty list if no matches
        """
        uri = params.text_document.uri
        position = params.position

        # Get the document text
        if uri not in server.documents:
            return CompletionList(is_incomplete=False, items=[])

        text = server.documents[uri]

        # Get the prefix up to the cursor
        prefix = get_prefix_at_position(text, position)

        # Check if we're completing tt. variables
        TT_PREFIX = "{{ tt."
        if TT_PREFIX in prefix:
            # Extract the partial variable name after "{{ tt."
            tt_start = prefix.rfind(TT_PREFIX)
            template_rest = prefix[tt_start:]

            # Check we haven't closed the template yet
            if "}}" in template_rest:
                close_index = template_rest.index("}}")
                # If }} is before or at the tt. prefix end, we're outside the template
                if close_index <= len(TT_PREFIX):
                    return CompletionList(is_incomplete=False, items=[])

            partial = prefix[tt_start + len(TT_PREFIX):]

            # Strip any trailing }} from partial if present
            if "}}" in partial:
                partial = partial[:partial.index("}}")]

            # Filter builtin variables by partial match
            items = []
            for var_name in BUILTIN_VARIABLES:
                if var_name.startswith(partial):
                    items.append(
                        CompletionItem(
                            label=var_name,
                            kind=CompletionItemKind.Variable,
                            detail=f"Built-in variable: {{ tt.{var_name} }}",
                            insert_text=var_name,
                        )
                    )

            return CompletionList(is_incomplete=False, items=items)

        # Check if we're completing var. variables
        VAR_PREFIX = "{{ var."
        if VAR_PREFIX in prefix:
            # Extract the partial variable name after "{{ var."
            var_start = prefix.rfind(VAR_PREFIX)
            template_rest = prefix[var_start:]

            # Check we haven't closed the template yet
            if "}}" in template_rest:
                close_index = template_rest.index("}}")
                # If }} is before or at the var. prefix end, we're outside the template
                if close_index <= len(VAR_PREFIX):
                    return CompletionList(is_incomplete=False, items=[])

            partial = prefix[var_start + len(VAR_PREFIX):]

            # Strip any trailing }} from partial if present
            if "}}" in partial:
                partial = partial[:partial.index("}}")]

            # Extract variables from the document
            variables = extract_variables(text)

            # Filter variables by partial match
            items = []
            for var_name in variables:
                if var_name.startswith(partial):
                    items.append(
                        CompletionItem(
                            label=var_name,
                            kind=CompletionItemKind.Variable,
                            detail=f"User variable: {{ var.{var_name} }}",
                            insert_text=var_name,
                        )
                    )

            return CompletionList(is_incomplete=False, items=items)

        return CompletionList(is_incomplete=False, items=[])

    # Store handler references for testing
    server.handlers["initialize"] = initialize
    server.handlers["shutdown"] = shutdown
    server.handlers["exit"] = exit
    server.handlers["textDocument/didOpen"] = did_open
    server.handlers["textDocument/didChange"] = did_change
    server.handlers["textDocument/completion"] = completion

    return server


def main() -> None:
    """Start the tasktree LSP server."""
    server = create_server()
    server.start_io()


if __name__ == "__main__":
    main()
