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

- **Top-level structure**: Only `imports`, `environments`, `variables`, and `tasks` are allowed at root
- **Required fields**: Tasks must have a `cmd` field
- **Field types**: Ensures strings, arrays, and objects are used correctly
- **Naming patterns**: Task names and namespaces must match `^[a-zA-Z][a-zA-Z0-9_-]*$`
- **Named inputs/outputs**: Supports both anonymous (strings) and named (objects) format
- **Self-references**: Named inputs/outputs can be referenced with `{{ self.inputs.name }}` and `{{ self.outputs.name }}`
- **Dependency outputs**: Named outputs can be referenced with `{{ dep.task.outputs.name }}`
- **Environment requirements**: Environments must specify a `shell` (or `dockerfile` for Docker environments)

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
    inputs:
      - sources: "src/**/*.rs"        # Named input - can use {{ self.inputs.sources }}
    outputs:
      - binary: target/release/bin    # Named output - can be referenced
      - target/release/bin.map        # Anonymous output
    cmd: cargo build --release --manifest-path {{ self.inputs.sources }}/../Cargo.toml

  test:
    desc: Run tests
    deps: [build]
    cmd: cargo test

  package:
    desc: Package the application
    deps: [build]
    inputs:
      - manifest: package.yaml        # Named input
    outputs:
      - archive: dist/app.tar.gz      # Named output
    cmd: |
      mkdir -p dist
      # Use self-references for own inputs/outputs
      tar czf {{ self.outputs.archive }} \
        {{ dep.build.outputs.binary }} \
        {{ self.inputs.manifest }}

  deploy:
    desc: Deploy to environment
    deps: [package]
    args: [environment, region=us-west-1]
    cmd: |
      echo "Deploying to {{ arg.environment }} in {{ arg.region }}"
      # Reference named output from dependency
      scp {{ dep.package.outputs.archive }} server:/opt/
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
