# Work Item 2: Environment Variable Type in Variables Section

## Overview

Extend the `variables` section to support reading values from environment variables using the `{ env: VAR_NAME }` syntax.

## Requirements

### 1. YAML Schema Extension

Add support for environment variable references in the `variables` section:

```yaml
variables:
  # Simple variables (from Work Item 1)
  server: "production.example.com"
  port: 8080
  
  # Environment variable references (new)
  api_key: { env: API_KEY }
  db_password: { env: DATABASE_PASSWORD }
  
  # Can be used in other variable definitions
  connection_string: "postgres://user:{{ var: db_password }}@localhost/db"

tasks:
  deploy:
    cmd: 'curl -H "Authorization: Bearer {{ var.api_key }}" {{ var.server }}'
```

### 2. Environment Variable Resolution

**Parse-time behavior:**
- Environment variables are resolved at recipe parse time (when `tt` starts)
- The value is the current environment variable value at parse time
- If `tt` is invoked as `API_KEY=foo tt task`, that value is captured

**Example:**
```bash
export API_KEY="secret123"
tt deploy  # api_key variable will contain "secret123"
```

**Undefined environment variables:**
Two possible approaches (choose one):
Error if environment variable is not set
```python
# Raises clear error: "Environment variable 'API_KEY' is not set"
```

### 4. Type Handling

**Environment variable values are always strings:**
- `{ env: PORT }` where `PORT=8080` in environment → variable value is string `"8080"`
- Unlike simple variables where `port: 8080` is an integer
- This is consistent with how environment variables work in shells

**Variable-in-variable with env:**
```yaml
variables:
  port: { env: PORT }
  url: "http://localhost:{{ var.port }}"
```
If `PORT=8080`, then `url` becomes `"http://localhost:8080"` (string substitution).

### 5. Validation

Add validation for:
- `{ env: VAR_NAME }` syntax correctness
- Environment variable name validity (typically uppercase alphanumeric + underscore)
- Clear error if environment variable is not set
- Ensure `env` is the only key in the dictionary (reject `{ env: VAR, other: thing }`)

**Invalid examples:**
```yaml
variables:
  bad1: { env: }  # Missing variable name
  bad2: { env: VAR, default: "x" }  # Extra keys not supported
  bad3: { env: "VAR NAME" }  # Spaces in env var name
```

### 6. Testing Requirements

**Unit tests should cover:**
- Basic env variable resolution: `{ env: TEST_VAR }`
- Multiple env variables in same recipe
- Env variable used in other variable definitions
- Error when environment variable is not set
- Variable-in-variable expansion with env values
- Type behavior (env values are always strings)

**Integration tests should verify:**
- Environment variables available in task commands via `{{ var.name }}`
- Environment variables resolved at correct time (parse time)
- Works with variable-in-variable expansion
- Works across imported files (if applicable)

### 7. Error Messages

**Clear error messages for common issues:**

```
Environment variable 'API_KEY' (referenced by variable 'api_key') is not set
Hint: Set it before running tt:
  API_KEY=value tt task
  
Or export it in your shell:
  export API_KEY=value
  tt task
```

```
Invalid environment variable reference: { env: }
Expected: { env: VARIABLE_NAME }
In variable: 'my_var'
```

### 8. Documentation Updates

**README.md additions:**

```markdown
### Environment Variables in Variables Section

Variables can reference environment variables:

```yaml
variables:
  api_key: { env: API_KEY }
  db_host: { env: DATABASE_HOST }
  connection: "{{ var.db_host }}:5432"
```

Environment variables are resolved when `tt` starts:

```bash
export API_KEY="secret123"
tt deploy  # api_key contains "secret123"
```

**Note:** Environment variable values are always strings, even if they look like numbers.
```

**Document the difference:**
- Simple variables: `port: 8080` → integer value
- Env variables: `{ env: PORT }` → string value (even if PORT=8080)

### 9. Implementation Notes

**Environment variable lookup:**
- Use `os.environ.get(var_name)` in Python
- Check for `None` (not set) vs empty string (set to empty)
- Both should probably be treated the same way for simplicity

**Ordering still matters:**
```yaml
variables:
  base: { env: BASE_URL }
  users: "{{ var.base }}/users"  # OK: base is defined first
```

**Security consideration:**
- Document that secrets in environment variables will be visible in process listings
- This is standard shell behavior, but worth mentioning

## Success Criteria

- [ ] `{ env: VAR_NAME }` syntax parses correctly
- [ ] Environment variables resolve to their values at parse time
- [ ] Clear error when environment variable is not set
- [ ] Env variables work in variable-in-variable expansion
- [ ] All environment variable values are strings
- [ ] All tests pass
- [ ] Documentation updated with examples
