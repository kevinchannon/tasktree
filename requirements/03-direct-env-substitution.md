# Work Item 3: Direct Environment Variable Substitution in Tasks

## Overview

Add support for directly referencing environment variables in task commands using the `{{ env.VAR_NAME }}` syntax, without needing to define them in the `variables` section first.
## Requirements

### 1. Syntax

Add `{{ env.VAR_NAME }}` as a third substitution type alongside `{{ arg.name }}` and `{{ var.name }}`:

```yaml
tasks:
  deploy:
    args: [target]
    cmd: |
      echo "Deploying to {{ arg.target }}"
      echo "User: {{ env.USER }}"
      echo "Home: {{ env.HOME }}"
      scp package.tar.gz {{ env.DEPLOY_USER }}@{{ arg.target }}:/opt/
```

### 2. Resolution Behavior

**Key difference from `{ env: VAR }` in variables section:**

- **Variables section**: Resolved at parse time, value is captured when `tt` starts
- **Direct usage**: Resolved at substitution time (just before execution)
- **Syntax difference**: Follows the established substitution syntax established for arg and var. So: {{ env.NAME }} 

**Why the difference?**
This allows environment variables to be set differently for different tasks if needed (though this is an edge case). More importantly, it's simpler to implement and understand.

**Example:**
```yaml
tasks:
  show-user:
    cmd: echo "Running as {{ env.USER }}"
```

```bash
tt show-user  # Uses current $USER value
```

### 3. Undefined Environment Variables

**Behavior when environment variable is not set:**

**Recommended approach (strict):**
- Error at substitution time if environment variable is undefined
- Provides clear error: `Environment variable 'DEPLOY_USER' is not set`

### 4. Where Environment Substitution Works

Environment variable substitution should work in the same places as arg and var

### 5. Validation

Add validation for:
- Valid environment variable names (typically uppercase alphanumeric + underscore)
- Clear error messages when env var not set

### 7. Testing Requirements

**Unit tests should cover:**
- Basic env substitution: `{{ env.USER }}`
- Multiple env vars in same command
- Mixed substitution types: `{{ arg.x }} {{ var.y }} {{ env.Z }}`
- Error when environment variable not set
- Env substitution in different fields (cmd, desc, working_dir)

**Integration tests should verify:**
- Environment variables work in actual task execution
- Values are current at execution time
- Works with multiline commands
- Works in Docker environments (if applicable)

**Two ways to use environment variables:**

1. **Via variables section**:
   ```yaml
   variables:
     api_key: { env: API_KEY }
   
   tasks:
     deploy:
       cmd: 'curl -H "Authorization: {{ var.api_key }}"'
   ```
   - Resolved at parse time
   - Can be used in variable-in-variable expansion
   - More verbose but more explicit
2. **String substitution in variable section:**
   ```yaml
   variables:
     api_key: "{{ env.API_KEY }}"
   
   tasks:
     deploy:
       cmd: 'curl -H "Authorization: {{ var.api_key }}"'
   ```
3**Direct substitution** (this work item):
   ```yaml
   tasks:
     deploy:
       cmd: 'curl -H "Authorization: {{ env.API_KEY }}"'
   ```
   - Resolved at substitution time
   - More concise
   - Direct and obvious

**When to use which:**
- Use variables section when you need to compose values or use them in multiple places
- Use direct substitution for simple, one-off environment variable references

Both should be documented and supported.

### 9. Error Messages

**Clear, actionable error messages:**

```
Environment variable 'DEPLOY_USER' is not set

In task: deploy
Command: scp package.tar.gz {{ env.DEPLOY_USER }}@server:/opt/

Set the variable before running:
  DEPLOY_USER=admin tt deploy
```

### 10. Documentation Updates

**README.md additions:**

```markdown
### Environment Variables in Tasks

Tasks can directly reference environment variables:

```yaml
tasks:
  deploy:
    cmd: scp package.tar.gz {{ env.DEPLOY_USER }}@{{ arg.server }}:/opt/
```

```bash
export DEPLOY_USER=admin
tt deploy production
```

**Two ways to use environment variables:**

1. **Direct reference** (for simple cases):
   ```yaml
   cmd: echo {{ env.USER }}
   ```

2. **Via variables section** (for composition/reuse):
   ```yaml
   variables:
     user: "{{ env.USER }}"
     home: { env: HOME }
     config: "{{ var.home }}/.config"
   ```

### 11. Implementation Notes

**Substitution order doesn't matter:**
All three types can be resolved in a single pass since none depend on each other within a single template string.

### 12. Files to Modify

## Success Criteria

- [ ] `{{ env: VAR }}` syntax works in task commands
- [ ] Environment variables resolve to current values
- [ ] Clear error when environment variable is not set
- [ ] Works alongside `{{ arg: }}` and `{{ var: }}` substitutions
- [ ] All tests pass
- [ ] Documentation and examples shows both env variable approaches
