# Task Tree YAML Schema

This directory contains the JSON Schema for Task Tree recipe files (`tasktree.yaml` or `tt.yaml`).

## What is a YAML Schema?

The JSON Schema provides:
- **Autocomplete**: Get suggestions for task fields as you type
- **Validation**: Immediate feedback on syntax errors
- **Documentation**: Hover over fields to see descriptions
- **Type checking**: Ensure values match expected types

## Usage

### VS Code

For your project, copy the settings from `schema/vscode-settings-snippet.json` to your `.vscode/settings.json`:

```json
{
  "yaml.schemas": {
    "https://raw.githubusercontent.com/kevinchannon/tasktree/main/schema/tasktree-schema.json": [
      "tasktree.yaml",
      "tt.yaml"
    ]
  }
}
```

Or add a comment at the top of your `tasktree.yaml`:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/kevinchannon/tasktree/main/schema/tasktree-schema.json

tasks:
  build:
    cmd: cargo build
```

### IntelliJ / PyCharm

1. Go to **Settings → Languages & Frameworks → Schemas and DTDs → JSON Schema Mappings**
2. Add new mapping:
   - **Name**: Task Tree
   - **Schema file**: Point to `schema/tasktree-schema.json`
   - **Schema version**: JSON Schema version 7
   - **File path pattern**: `*.tasks`, `tasktree.yaml`, `tt.yaml`, `tasktree.yml` or `tt.yml`

### Command Line Validation

You can validate your recipe files using tools like `check-jsonschema`:

```bash
# Install
pip install check-jsonschema

# Validate
check-jsonschema --schemafile schema/tasktree-schema.json tasktree.yaml
```

## Schema Features

The schema validates:

- **Top-level structure**: Only `imports`, `environments`, and `tasks` are allowed at root
- **Required fields**: Tasks must have a `cmd` field
- **Field types**: Ensures strings, arrays, and objects are used correctly
- **Naming patterns**: Task names and namespaces must match `^[a-zA-Z][a-zA-Z0-9_-]*$`
- **Environment requirements**: Environments must specify a `shell`

## Example

```yaml
imports:
  - file: common/base.yaml
    as: base

environments:
  default: bash-strict
  bash-strict:
    shell: /bin/bash
    args: ['-e', '-u', '-o', 'pipefail']

tasks:
  build:
    desc: Build the application
    deps: [base.setup]
    inputs: ["src/**/*.rs"]
    outputs:
      - binary: target/release/bin    # Named output - can be referenced
      - target/release/bin.map        # Anonymous output
    cmd: cargo build --release

  test:
    desc: Run tests
    deps: [build]
    cmd: cargo test

  deploy:
    desc: Deploy to environment
    deps: [build]
    args: [environment, region=us-west-1]
    cmd: |
      echo "Deploying to {{ arg.environment }} in {{ arg.region }}"
      # Reference named output from dependency
      scp {{ dep.build.outputs.binary }} server:/opt/
      ./deploy.sh {{ arg.environment }} {{ arg.region }}
```

## Contributing

If you find issues with the schema or want to improve it, please:

1. Update `tasktree-schema.json`
2. Test with your editor
3. Submit a pull request

## References

- [JSON Schema Specification](https://json-schema.org/)
- [VS Code YAML Extension](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)
- [YAML Language Server](https://github.com/redhat-developer/yaml-language-server)
