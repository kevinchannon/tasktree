# Work Item 1: Basic Variables with Simple Values

## Overview

Add a new top-level `variables` section to the recipe YAML that supports simple key-value pairs. Update the substitution syntax throughout the codebase to use explicit prefixes (`{{ arg.name }}` and `{{ var.name }}`).

## Requirements

### 1. YAML Schema Changes

Add support for a top-level `variables` section in recipe files:

```yaml
variables:
  server: "production.example.com"
  port: 8080
  debug: true
  timeout: 30.5

tasks:
  deploy:
    args: [target]
    cmd: echo "Deploying to {{ var.server }} on port {{ var.port }}"
```

**Supported variable types:**
Allowed variable types should match those allowed in task arguments: 
* int - an integer value (e.g. 0, 10, 123, -9)
* float - a floating point value (e.g. 1.234, -3.1415, 2e-4)
* bool - Boolean-ish value (e.g. true, false, yes, no, 1, 0, etc)
* str - a string
* path - a pathlike string
* datetime - a datetime in the format 2025-12-17T16:56:12
* ip - an ip address (v4 or v6)
* ipv4 - an IPv4 value
* ipv6 - an IPv6 value
* email - String validated, but not positively confirmed to be a reachable address.
* hostname - looks like a hostname, resolution of the name is not attempted as part of the validation

### 2. Variable Resolution

**Parse-time resolution:**
- Variables must be resolved at recipe parse time, after YAML loading but before task execution planning
- Variables are defined in order and can reference previously-defined variables
- Variable references in variable definitions must use the `{{ var.name }}` syntax
- Undefined variable references should produce a clear error, e.g. "Variable 'varX' references undefined variable 'varY'. Variables must be defined before use."

**Example with variable-in-variable:**
```yaml
variables:
  base_url: "https://api.example.com"
  users_endpoint: "{{ var.base_url }}/users"
  posts_endpoint: "{{ var.base_url }}/posts"
```

**Ordering requirement:**
Variables must be defined before they are referenced. This example should error:
```yaml
variables:
  derived: "{{ var.base }}"  # Error: 'base' not yet defined
  base: "value"
```

### 3. Substitution Syntax Changes

**Current syntax:** `{{ arg_name }}`
**New syntax:** `{{ arg.arg_name }}` and `{{ var.var_name }}`

**Substitution locations:**
Variable and argument substitutions should work in:
- Task fields: `cmd`, `desc`, `inputs`, `outputs`, `working_dir`
- Task argument default values
- Environment `preamble` fields
- Other variable definitions (as shown above)

**Type handling:**
- All substitutions stringify their values at substitution time
- `{{ var.port }}` where `port: 8080` becomes the string `"8080"`
- `{{ var.debug }}` where `debug: true` becomes the string `"true"`

### 4. Validation

Add validation to ensure:
- Variable names are valid identifiers (alphanumeric + underscore, not starting with digit)
- Variable values are one of the supported types.
- No circular references in variable definitions
- Clear error messages for:
  - Undefined variable references
  - Invalid variable names
  - Unsupported variable types

### 5. Testing Requirements

**Unit tests should (at least) cover:**
- Simple variable definition and substitution
- All supported variable types (str, int, float, bool)
- Variable-in-variable expansion
- Proper ordering (defined before use)
- Error cases:
  - Reference to undefined variable
  - Circular references (if detectable at parse time)
  - Invalid variable names

**Integration tests should verify:**
- Variables work in task commands
- Variables work in task descriptions
- Variables work in working_dir paths
- Variables work in argument defaults
- Variables work in environment preambles
- Variable substitution happens before task execution

### 6. Backward Compatibility

**Breaking change:** The substitution syntax changes from `{{ name }}` to `{{ arg.name }}`.

DO NOT be concerned with handling the old syntax going forward, no parsing of the old syntax is required. No warnings about the old syntax need be issued. The product is in early alpha and has not real users, so we do not need to concern ourselves with compatibility issues.

### 7. Documentation Updates

Update README.md and other docs to:
- Document the `variables` section
- Show examples of variable definition and usage
- Explain variable-in-variable expansion
- Document ordering requirements
- Update all examples to use new `{{ arg.name }}` syntax
- Explain type handling (all substitutions produce strings)

## Implementation Notes

- Variables are global to the recipe (not scoped to tasks)
- Variable resolution happens once at recipe parse time, not per-task
- String interpolation should be simple string replacement after stringification

## Success Criteria

- [ ] Variables section parses correctly from YAML
- [ ] All variable types work as expected
- [ ] Variable-in-variable expansion works with proper ordering
- [ ] New substitution syntax works in all specified locations
- [ ] Clear errors for undefined variables
- [ ] All tests pass
- [ ] Documentation and examples updated
