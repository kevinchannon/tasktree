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
from tasktree.lsp.position_utils import (
    get_prefix_at_position,
    is_in_cmd_field,
    is_in_substitutable_field,
    get_task_at_position,
)
from tasktree.lsp.parser_wrapper import (
    extract_variables,
    extract_task_args,
    extract_task_inputs,
    extract_task_outputs,
)

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

    def _complete_template_variables(
        prefix: str,
        template_prefix: str,
        variable_names: list[str],
        variable_kind: str,
    ) -> CompletionList:
        """Shared logic for template variable completion.

        Args:
            prefix: The text prefix up to the cursor position
            template_prefix: The template prefix to match (e.g., "{{ tt." or "{{ var.")
            variable_names: List of available variable names
            variable_kind: Description of variable type (e.g., "Built-in" or "User")

        Returns:
            CompletionList containing matching completion items, or empty list if no matches
        """
        if template_prefix not in prefix:
            return CompletionList(is_incomplete=False, items=[])

        # Extract the partial variable name after the template prefix
        prefix_start = prefix.rfind(template_prefix)
        template_rest = prefix[prefix_start:]

        # Check we haven't closed the template yet
        if "}}" in template_rest:
            close_index = template_rest.index("}}")
            # If }} is before or at the prefix end, we're outside the template
            if close_index <= len(template_prefix):
                return CompletionList(is_incomplete=False, items=[])

        partial = prefix[prefix_start + len(template_prefix):]

        # Strip any trailing }} from partial if present
        if "}}" in partial:
            partial = partial[:partial.index("}}")]

        # Filter variables by partial match
        items = []
        for var_name in variable_names:
            if var_name.startswith(partial):
                # Extract the variable prefix for the detail (e.g., "tt" or "var")
                var_prefix = template_prefix.replace("{{ ", "").replace(".", "")
                items.append(
                    CompletionItem(
                        label=var_name,
                        kind=CompletionItemKind.Variable,
                        detail=f"{variable_kind} variable: {{{{ {var_prefix}.{var_name} }}}}",
                        insert_text=var_name,
                    )
                )

        return CompletionList(is_incomplete=False, items=items)

    @server.feature("textDocument/completion")
    def completion(params: CompletionParams) -> CompletionList:
        """Handle completion request.

        Provides context-aware completions for tasktree YAML files.
        Currently supports:
        - tt.* built-in variable completion
        - var.* user-defined variable completion
        - arg.* task argument completion (only inside task cmd fields)
        - self.inputs.* named input completion (only inside task cmd fields)
        - self.outputs.* named output completion (only inside task cmd fields)

        Completion behavior:
        - Completions filter by partial match after the prefix (e.g., "{{ var.my" → only "my*" variables)
        - Returns empty list if template is already closed (cursor after }})
        - Trailing }} in partial names are automatically stripped for matching
        - arg.*, self.inputs.*, and self.outputs.* completions are only provided when cursor is inside a task's cmd field

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

        # Try tt.* built-in variable completion
        if "{{ tt." in prefix:
            return _complete_template_variables(
                prefix, "{{ tt.", BUILTIN_VARIABLES, "Built-in"
            )

        # Try var.* user-defined variable completion
        if "{{ var." in prefix:
            variables = extract_variables(text)
            return _complete_template_variables(
                prefix, "{{ var.", variables, "User"
            )

        # Try arg.* task argument completion (cmd, working_dir, args defaults)
        if "{{ arg." in prefix:
            # arg.* is valid in cmd, working_dir, and args[].default fields
            if not is_in_substitutable_field(text, position):
                return CompletionList(is_incomplete=False, items=[])

            # Get the task name at this position
            task_name = get_task_at_position(text, position)
            if task_name is None:
                return CompletionList(is_incomplete=False, items=[])

            # Extract args for this task
            args = extract_task_args(text, task_name)
            return _complete_template_variables(
                prefix, "{{ arg.", args, "Task argument"
            )

        # Try self.inputs.* named input completion (cmd, working_dir, args defaults)
        if "{{ self.inputs." in prefix:
            # self.inputs.* is valid in cmd, working_dir, and args[].default fields
            if not is_in_substitutable_field(text, position):
                return CompletionList(is_incomplete=False, items=[])

            # Get the task name at this position
            task_name = get_task_at_position(text, position)
            if task_name is None:
                return CompletionList(is_incomplete=False, items=[])

            # Extract named inputs for this task
            inputs = extract_task_inputs(text, task_name)
            return _complete_template_variables(
                prefix, "{{ self.inputs.", inputs, "Task input"
            )

        # Try self.outputs.* named output completion (cmd, working_dir, args defaults)
        if "{{ self.outputs." in prefix:
            # self.outputs.* is valid in cmd, working_dir, and args[].default fields
            if not is_in_substitutable_field(text, position):
                return CompletionList(is_incomplete=False, items=[])

            # Get the task name at this position
            task_name = get_task_at_position(text, position)
            if task_name is None:
                return CompletionList(is_incomplete=False, items=[])

            # Extract named outputs for this task
            outputs = extract_task_outputs(text, task_name)
            return _complete_template_variables(
                prefix, "{{ self.outputs.", outputs, "Task output"
            )

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
