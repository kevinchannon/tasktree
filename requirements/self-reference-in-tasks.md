# Self-Referential Input/Output Templates

## Rationale

Tasks currently require repeating input and output paths in both the declaration and the command string. This creates maintenance burden, particularly when paths contain variable substitutions or when tasks have multiple inputs/outputs. The DRY violation becomes acute when version strings or other dynamic components appear in output filenames.

This feature adds `{{ self.inputs.name }}` and `{{ self.outputs.name }}` template syntax to allow tasks to reference their own declared inputs and outputs within command strings.

## Requirements

### Core Functionality

- Add `self.inputs` and `self.outputs` to the template substitution context for task commands
- Support named inputs and outputs only (anonymous entries remain non-referenceable via templates)
- Perform string substitution of the literal path/glob expression as declared in YAML
- No path resolution, glob expansion, or filesystem validation during template substitution
- Parse-time validation that referenced names actually exist in the task's inputs/outputs declarations

### Template Syntax

- `{{ self.inputs.name }}` substitutes the path/glob string from a named input
- `{{ self.outputs.name }}` substitutes the path/glob string from a named output
- Follows existing template prefix conventions (`var`, `env`, `arg`, `dep`, `tt`)

### Validation Behaviour

- Error at parse time (or execution plan construction) if template references non-existent input/output name
- No validation of path existence, path validity, or glob pattern correctness
- Template expansion occurs before command execution (consistent with all other template types)

### Glob Handling

- Glob patterns in inputs/outputs are substituted verbatim into the command string
- Shell expansion occurs at execution time (not during template substitution)
- Example: `inputs: [{src: "*.txt"}]` → `{{ self.inputs.src }}` → literal string `*.txt` in command

### Integration with Existing Features

- Works alongside existing template prefixes without conflict
- Compatible with variable substitution in input/output paths
- Named inputs/outputs structure already exists from previous work
- Does not affect anonymous inputs/outputs (they remain non-referenceable until positional access feature)

### Examples

For a task like:
```yaml
tasks:
  foo:
    inputs: [ foo_in.txt ]
    outputs: { x: foo_out.txt }
    cmd: cp foo_in.txt foo_out.txt

  bar:
    deps: [ foo ]
    inputs: [ bar_in.txt ]
    outputs: [ bar_out.txt ]
    cmd: |
      cp bar_in.txt bar_out.txt
      cat {{ dep.foo.outputs.x }} >> bar_out.txt
```
Using references to task inputs and outputs in the cmd, the above could become:
```yaml
tasks:
  foo:
    inputs: [ foo_in.txt ]
    outputs:
      - x: foo_out.txt
    cmd: cp foo_in.txt foo_out.txt

  bar:
    deps: [ foo ]
    inputs: [ {x: bar_in.txt} ] 
    outputs: [ {x: bar_out.txt} ]
    cmd: |
      cp {{ self.inputs.x }} {{ self.outputs.x }}
      cat {{ dep.foo.outputs.x }} >> {{ self.outputs.x }}
```
This allows a significant DRY advantage, especially if tasks have several inputs and outputs. Or, if the inputs and outputs are themselves defined by variables:

```yaml
variables:
  pkg_ver: { eval: "cat pkg/VERSION" }

tasks:
  foo:
    inputs: [ {app_files: "out/build/my-app/**/*"} ]
    outputs:
      - archive: "my-app-{{ var.pkg_ver }}.tar.gz"
    cmd: tar -czf {{ self.outputs.archive }} {{ self.inputs.app_files }}
```

## Acceptance Criteria

- [ ] Parse-time error when `{{ self.inputs.name }}` references non-existent input
- [ ] Parse-time error when `{{ self.outputs.name }}` references non-existent output  
- [ ] Named inputs can be referenced in command strings via `{{ self.inputs.name }}`
- [ ] Named outputs can be referenced in command strings via `{{ self.outputs.name }}`
- [ ] Glob patterns in inputs substitute verbatim (no expansion during template processing)
- [ ] Variable substitutions in input/output paths work before self-reference substitution
- [ ] Self-references work in tasks with mixed anonymous and named inputs/outputs
- [ ] Self-references work in tasks that are dependencies of other tasks
- [ ] Self-references work in tasks executed within Docker environments
- [ ] Documentation updated with self-reference syntax and examples
- [ ] Schema updated to reflect no syntax changes (feature uses existing named input/output structure)

## Edge Cases to Consider

### Mixed Anonymous and Named
Tasks with both anonymous and named inputs/outputs should work without interference. Only named entries are accessible via templates.

### Variable Composition
Input/output paths containing `{{ var.name }}` or other templates should resolve variables first, then allow self-reference to the fully-resolved path.

### Dependency Output References
Ensure `{{ dep.task.outputs.name }}` and `{{ self.outputs.name }}` can coexist in the same command without namespace collision.

### Nonexistent Names
Attempting to reference `{{ self.inputs.missing }}` when no input named "missing" exists should produce a clear error message indicating which task and which missing name.

### Empty Collections
Tasks with no inputs or no outputs should handle self-reference attempts gracefully (error if attempting to reference from empty collection).

### Case Sensitivity
Input/output names should be case-sensitive in references, consistent with YAML key behaviour.

### Working Directory Context
Self-references should substitute paths as declared, with no implicit resolution relative to working_dir or project_root.

## Testing Hints

### Unit Tests

- Template substitution with valid named inputs/outputs
- Error on reference to non-existent input name
- Error on reference to non-existent output name  
- Glob patterns substitute verbatim without expansion
- Mixed anonymous and named inputs/outputs
- Variable resolution in input/output paths before self-reference substitution
- Multiple self-references in single command
- Self-references in multi-line commands
- Empty input/output collections

### Integration Tests

- Task execution with self-referenced inputs/outputs produces correct output files
- Dependency chains where parent uses self-reference and child uses dep reference
- Docker environment tasks with self-referenced outputs
- Parameterised tasks with self-referenced inputs/outputs
- State management correctly handles tasks using self-references (cache invalidation)
- Force execution of task with self-references
- Dry-run display shows resolved self-references

### Regression Tests

- Existing tasks without self-references continue to work unchanged
- Dependency output references (`{{ dep.task.outputs.name }}`) unaffected
- Other template types (`var`, `env`, `arg`, `tt`) unaffected by addition of `self`