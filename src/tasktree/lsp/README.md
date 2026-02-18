# Tasktree Language Server (tt-lsp)

A Language Server Protocol (LSP) implementation for tasktree files, providing intelligent editor features like autocompletion for template variables and task references.

## Overview

The `tt-lsp` server enables IDE-like features for tasktree files (`.tt`, `.tasks`, `tasktree.yaml`, `.tasktree-config.yml`) in any LSP-compatible editor. It reuses tasktree's own parser to provide context-aware completions for template syntax.

## Features

### Template Variable Completion

The LSP server provides intelligent autocompletion for all tasktree template prefixes:

#### Built-in Variables (`tt.*`)

Complete all tasktree built-in variables anywhere in YAML files:

```yaml
tasks:
  build:
    cmd: echo {{ tt.█  # Completes: project_root, recipe_dir, task_name, working_dir, timestamp, etc.
```

Available built-in variables:
- `project_root` - Absolute path to project root
- `recipe_dir` - Directory containing the recipe file
- `task_name` - Name of currently executing task
- `working_dir` - Task's effective working directory
- `timestamp` - ISO8601 timestamp when task started
- `timestamp_unix` - Unix epoch timestamp
- `user_home` - Current user's home directory
- `user_name` - Current username

#### User-Defined Variables (`var.*`)

Complete variables defined in the `variables` section:

```yaml
variables:
  project_name: awesome-project
  build_dir: /tmp/build

tasks:
  build:
    cmd: echo {{ var.█  # Completes: project_name, build_dir
```

Works with all variable definition formats:
- Simple values: `var_name: value`
- Environment variables: `var_name: { env: ENV_VAR, default: fallback }`
- Runtime evaluation: `var_name: { eval: "command" }`
- File contents: `var_name: { read: path/to/file }`

#### Task Arguments (`arg.*`)

Complete arguments defined in the current task (context-aware, only inside `cmd` fields):

```yaml
tasks:
  build:
    args:
      - build_type:
          type: str
          choices: ["debug", "release"]
      - target
    cmd: cargo build --{{ arg.█  # Completes: build_type, target
```

**Important**:
- `arg.*` completions are scoped to the task containing the cursor. Arguments from other tasks are not suggested.
- `arg.*` completions are available in: `cmd`, `working_dir`, `outputs`, `deps`, and `args[].default` fields

**Example in different fields**:
```yaml
tasks:
  deploy:
    args: [app_name, version]
    outputs: ["deploy-{{ arg.app_name }}.log"]  # arg.* works in outputs
    deps:
      - process: [{{ arg.version }}]  # arg.* works in deps (parameterized dependencies)
    working_dir: /tmp/{{ arg.app_name }}  # arg.* works in working_dir
    cmd: echo "Deploy {{ arg.app_name }}"  # arg.* works in cmd
```

#### Named Inputs (`self.inputs.*`)

Complete named inputs defined in the current task (context-aware, available in substitutable fields):

```yaml
tasks:
  build:
    inputs:
      - source: src/main.c
      - header: include/defs.h
    cmd: gcc {{ self.inputs.█  # Completes: source, header
```

**Important**:
- Only **named** inputs are completed (e.g., `- source: path`). Anonymous inputs (e.g., `- path`) are not included.
- `self.inputs.*` completions are scoped to the task containing the cursor. Inputs from other tasks are not suggested.

#### Named Outputs (`self.outputs.*`)

Complete named outputs defined in the current task (context-aware, available in substitutable fields):

```yaml
tasks:
  build:
    outputs:
      - binary: dist/app
      - log: logs/build.log
    cmd: echo "Built {{ self.outputs.█  # Completes: binary, log
```

**Important**:
- Only **named** outputs are completed (e.g., `- binary: path`). Anonymous outputs (e.g., `- path`) are not included.
- `self.outputs.*` completions are scoped to the task containing the cursor. Outputs from other tasks are not suggested.

### Intelligent Context Awareness

- **Prefix filtering**: Completions filter by partial match (e.g., `{{ tt.time` → only `timestamp`, `timestamp_unix`)
- **Task scoping**: `arg.*`, `self.inputs.*`, and `self.outputs.*` completions are scoped to the task containing the cursor
- **Field-aware**: `arg.*`, `self.inputs.*`, and `self.outputs.*` completions are only available in fields that support substitution: `cmd`, `working_dir`, `outputs`, `deps`, and `args[].default`
- **Template boundaries**: No completions after closing `}}` braces
- **Graceful degradation**: Works with incomplete/malformed YAML during editing

## Installation

Tasktree includes `tt-lsp` as part of the main package. If you have tasktree installed via pipx, the LSP server is already available:

```bash
# Verify installation
which tt-lsp
# Should output: ~/.local/bin/tt-lsp (or similar)
```

## Editor Integration

The LSP server communicates over stdio using the Language Server Protocol. Configure your editor's LSP client to spawn `tt-lsp` for tasktree files.

### VS Code

Install a generic LSP client extension and configure it to use `tt-lsp`:

**.vscode/settings.json**:
```json
{
  "lsp.servers": {
    "tasktree": {
      "command": ["tt-lsp"],
      "filetypes": ["yaml"],
      "languageId": "yaml",
      "documentSelector": [
        {
          "language": "yaml",
          "pattern": "**/*.{tt,tasks}"
        },
        {
          "language": "yaml",
          "pattern": "**/tasktree.yaml"
        },
        {
          "language": "yaml",
          "pattern": "**/.tasktree-config.yml"
        }
      ]
    }
  }
}
```

### Neovim (nvim-lspconfig)

Add to your Neovim LSP configuration:

**~/.config/nvim/lua/lsp/tasktree.lua**:
```lua
local lspconfig = require('lspconfig')
local configs = require('lspconfig.configs')

-- Define tasktree LSP server
if not configs.tasktree then
  configs.tasktree = {
    default_config = {
      cmd = { 'tt-lsp' },
      filetypes = { 'yaml' },
      root_dir = lspconfig.util.root_pattern('tasktree.yaml', '.tasktree-config.yml', '.git'),
      settings = {},
    },
  }
end

-- Enable for tasktree files
lspconfig.tasktree.setup({
  autostart = true,
  on_attach = function(client, bufnr)
    -- Your on_attach configuration here
  end,
})

-- Auto-detect tasktree files and attach LSP
vim.api.nvim_create_autocmd({ "BufRead", "BufNewFile" }, {
  pattern = { "*.tt", "*.tasks", "tasktree.yaml", ".tasktree-config.yml" },
  callback = function()
    vim.bo.filetype = "yaml"
    vim.lsp.start({
      name = 'tasktree',
      cmd = { 'tt-lsp' },
      root_dir = vim.fs.dirname(vim.fs.find({'tasktree.yaml', '.git'}, { upward = true })[1]),
    })
  end,
})
```

### Helix

Add to **~/.config/helix/languages.toml**:

```toml
[[language]]
name = "yaml"
language-servers = ["yaml-language-server", "tasktree-lsp"]

[language-server.tasktree-lsp]
command = "tt-lsp"
```

### Sublime Text (LSP package)

Add to your LSP settings:

```json
{
  "clients": {
    "tasktree": {
      "enabled": true,
      "command": ["tt-lsp"],
      "selector": "source.yaml",
      "file_patterns": ["*.tt", "*.tasks", "tasktree.yaml", ".tasktree-config.yml"]
    }
  }
}
```

### Emacs (lsp-mode)

Add to your Emacs configuration:

```elisp
(with-eval-after-load 'lsp-mode
  (add-to-list 'lsp-language-id-configuration
               '("\\.\\(tt\\|tasks\\)\\'" . "yaml"))
  (lsp-register-client
   (make-lsp-client :new-connection (lsp-stdio-connection "tt-lsp")
                    :activation-fn (lsp-activate-on "yaml")
                    :priority -1
                    :server-id 'tasktree)))
```

## Usage

Once configured, the LSP server will automatically provide completions as you type in tasktree files:

1. Open a tasktree file (`.tt`, `.tasks`, `tasktree.yaml`, `.tasktree-config.yml`)
2. Type `{{ tt.` inside any YAML field → Get built-in variable completions
3. Type `{{ var.` inside any YAML field → Get user-defined variable completions
4. Type `{{ arg.` inside a task's `cmd` field → Get that task's argument completions

Completions update automatically as you modify the file (adding/removing variables, arguments, etc.).

## Architecture

The LSP server is built with:

- **pygls** - Python LSP framework for protocol handling
- **PyYAML** - YAML parsing (reuses tasktree's parser)
- **tasktree parser** - Direct reuse of tasktree's own parsing logic (no reimplementation)

### Module Structure

```
src/tasktree/lsp/
├── server.py              # LSP server main entry point and handlers
├── builtin_variables.py   # Built-in variable definitions (tt.*)
├── parser_wrapper.py      # YAML parsing for variable/arg extraction
└── position_utils.py      # Cursor position detection utilities
```

### How It Works

1. **Document Tracking**: Server stores opened/changed documents in memory
2. **Cursor Position Analysis**: Determines if cursor is inside a `cmd` field and which task
3. **YAML Parsing**: Extracts variables/arguments from document using tasktree's parser
4. **Prefix Matching**: Filters completions by partial prefix after template marker
5. **Completion Response**: Returns filtered CompletionItems to the editor

## Future Features

The following features are planned but not yet implemented:

- Environment variable completion (`env.*`)
- Dependency output completion (`dep.*.outputs.*`)
- Task name completion in `deps` lists
- Diagnostics (undefined variables, missing dependencies, circular deps)
- Go-to-definition for task references and imports
- Hover documentation for variables and tasks
- Syntax highlighting (TextMate grammar for template syntax)

## Troubleshooting

### LSP server not starting

1. Verify `tt-lsp` is on your PATH:
   ```bash
   which tt-lsp
   ```

2. Check your editor's LSP logs for error messages

3. Test the server manually:
   ```bash
   echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | tt-lsp
   ```
   Should output LSP initialization response

### No completions appearing

1. Ensure you're typing inside a tasktree file (`.tt`, `.tasks`, `tasktree.yaml`)
2. For `arg.*` completions, ensure cursor is inside a supported field (`cmd`, `working_dir`, `outputs`, `deps`, or `args[].default`)
3. Check that you're using the correct template syntax: `{{ prefix. }}`
4. Try closing and reopening the file to trigger re-parsing

### Completions not updating

The server operates in full-sync mode and should update on every change. If completions are stale:

1. Close and reopen the file
2. Restart the LSP server (editor-specific command)
3. Check editor LSP logs for YAML parsing errors

## Development

For information on developing and extending the LSP server, see the [Developer Guide](../../../README.md) and [CLAUDE.md](../../../CLAUDE.md).

### Testing

The LSP implementation includes comprehensive tests:

```bash
# Unit tests (server logic, parsing, position detection)
pytest tests/unit/test_lsp_*.py

# Integration tests (full LSP workflows)
pytest tests/integration/test_lsp_*.py

# E2E tests (subprocess execution)
pytest tests/e2e/test_lsp_*.py
```

## License

Part of the tasktree project. See [LICENSE](../../../LICENSE) for details.
