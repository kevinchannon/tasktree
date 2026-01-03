# Work Item 4: File Read Variable Type

## Overview

Extend the `variables` section to support reading values from files using the `{ read: filepath }` syntax.

## Requirements

### 1. YAML Schema Extension

Add support for reading file contents into variables:

```yaml
variables:
  # Simple variables
  server: "production.example.com"
  
  # Read from files
  api_key: { read: secrets/api-key.txt }
  ssh_key: { read: ~/.ssh/deploy_key }
  version: { read: VERSION }
  
  # Can be used in other variables
  auth_header: "Bearer {{ var.api_key }}"

tasks:
  deploy:
    cmd: |
      curl -H "Authorization: {{ var.auth_header }}" \
           {{ var.server }}/deploy
```

### 2. File Reading Behavior

**Parse-time resolution:**
- Files are read at recipe parse time (when `tt` starts)
- File contents are cached in the resolved variables dictionary
- If file content changes, user must re-run `tt` to pick up the change

**File content handling:**
- Read entire file as UTF-8 text
- Strip trailing newline (if present) for convenience
  - `secrets/key.txt` containing `"secret123\n"` becomes `"secret123"`
  - Common pattern: `echo "value" > file` adds a trailing newline
- Preserve other whitespace (leading/trailing spaces, internal newlines)

**Example:**
```bash
echo "my-secret-key" > api-key.txt  # Has trailing newline
```
```yaml
variables:
  key: { read: api-key.txt }  # key = "my-secret-key" (newline stripped)
```

### 3. Path Resolution

**File paths are relative to:**
1. Recipe file location (not current working directory)
2. This matches behavior of other file references in tasktree

**Example:**
```
project/
  tasktree.yaml
  secrets/
    api-key.txt
  tasks/
    deploy.yaml
```

In `tasktree.yaml`:
```yaml
variables:
  key: { read: secrets/api-key.txt }  # Relative to tasktree.yaml
```

**Absolute paths:**
- Should also be supported: `{ read: /etc/hostname }`
- Tilde expansion: `{ read: ~/.ssh/key }` should expand to user's home directory

### 4. Error Handling

**File not found:**
```
Failed to read file for variable 'api_key': secrets/api-key.txt
File not found: /absolute/path/to/project/secrets/api-key.txt

Ensure the file exists relative to the recipe file location.
```

**Permission denied:**
```
Failed to read file for variable 'ssh_key': ~/.ssh/deploy_key  
Permission denied

Ensure the file is readable by the current user.
```

**Invalid UTF-8:**
```
Failed to read file for variable 'data': binary-file.dat
File contains invalid UTF-8 data

The { read: ... } syntax only supports text files.
```

**Recommendation:** Fail fast and loudly. Don't silently substitute empty strings.

### 6. Type Handling

**File read values are always strings:**
- Even if file contains `8080`, the variable value is string `"8080"`
- Consistent with environment variable behavior
- User can do manual type conversion in their commands if needed

### 7. Security Considerations

**Document potential risks:**
- Recipe files can read any file the user has permission to read
- Be cautious with recipes from untrusted sources

**Best practices to document:**
- Don't commit secret files to version control
- Use `.gitignore` for secret files
- Consider using environment variables for secrets instead

### 8. Validation

Add validation for:
- `{ read: filepath }` syntax correctness
- Filepath must be a string
- Ensure `read` is the only key in the dictionary

**Invalid examples:**
```yaml
variables:
  bad1: { read: }  # Missing filepath
  bad2: { read: file.txt, default: "x" }  # Extra keys not supported
  bad3: { read: 123 }  # Filepath must be string
```

### 9. Testing Requirements

**Unit tests should cover:**
- Basic file reading: `{ read: test.txt }`
- Trailing newline stripping
- Relative path resolution (relative to recipe file)
- Absolute path support
- Tilde expansion in paths
- Error when file doesn't exist
- Error when file is not readable (permission test may be tricky)
- Error when file is not valid UTF-8
- File content used in variable-in-variable expansion

**Integration tests should verify:**
- File content available in task commands
- Works with variable-in-variable expansion
- Paths resolve correctly from recipe location

### 10. Edge Cases

**Empty files:**
```bash
touch empty.txt  # File exists but is empty
```
```yaml
variables:
  empty: { read: empty.txt }  # empty = ""
```
Should work fine - empty string is valid.

**Files with only a newline:**
```bash
echo "" > newline.txt  # Contains just "\n"
```
```yaml
variables:
  newline: { read: newline.txt }  # newline = ""
```
Trailing newline stripped, result is empty string.

**Binary files:**
Should error with clear message about UTF-8 requirement.

**Symbolic links:**
Should follow symlinks normally (Python's `Path.read_text()` does this by default).

### 11. Documentation Updates

**README.md additions:**

```markdown
### Reading Files into Variables

Variables can be populated from file contents:

```yaml
variables:
  api_key: { read: secrets/api-key.txt }
  version: { read: VERSION }
  ssh_key: { read: ~/.ssh/deploy_key }
```

**Path resolution:**
- Relative paths are resolved from the recipe file location
- Absolute paths and tilde (`~`) expansion are supported

**Behavior:**
- Files are read at parse time (when `tt` starts)
- Trailing newline is automatically stripped for convenience
- File must contain valid UTF-8 text

**Security note:**
Recipe files can read any file you have permission to read. Be cautious with recipes from untrusted sources.

**Alternatives for secrets:**
- Use environment variables: `{ env: API_KEY }`
- Use a secrets manager: `{ eval: "vault read -field=token secret/api" }`

### 12. Implementation Notes

**Newline stripping logic:**
Only strip a single trailing newline. Don't use `rstrip()` which would strip all trailing whitespace.

**Path resolution:**
Use `Path.expanduser()` for tilde expansion and check `is_absolute()` to handle absolute vs relative paths.

### 13. Files to Modify

## Success Criteria

- [ ] `{ read: filepath }` syntax parses correctly
- [ ] Files are read from paths relative to recipe file
- [ ] Absolute paths and tilde expansion work
- [ ] Trailing newline is stripped
- [ ] Clear errors for missing/unreadable/binary files
- [ ] File content works in variable-in-variable expansion
- [ ] All tests pass
- [ ] Documentation and examples includes security considerations
