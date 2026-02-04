import re
from pathlib import Path

def refactor_content(content):
    """Apply refactoring rules to content."""
    # Replace imports
    content = re.sub(r'from tasktree\.parser import ([^\n]*\bEnvironment\b[^\n]*)',
                     lambda m: m.group(0).replace('Environment', 'Runner'), content)

    # Replace type hints
    content = re.sub(r':\s*Environment(?=\s|,|\)|\]|$)', ': Runner', content)
    content = re.sub(r'dict\[str,\s*Environment\]', 'dict[str, Runner]', content)

    # Replace YAML field names - must be careful with indentation
    content = re.sub(r'^(\s*)environments:(\s*)$', r'\1runners:\2', content, flags=re.MULTILINE)
    content = re.sub(r'^(\s+)env:(\s+)', r'\1run_in:\2', content, flags=re.MULTILINE)

    # Replace method calls
    content = re.sub(r'\.get_environment\(', '.get_runner(', content)
    content = re.sub(r'\.environments\b', '.runners', content)

    # Replace function names
    content = re.sub(r'\bhash_environment_definition\b', 'hash_runner_definition', content)
    content = re.sub(r'\bis_docker_environment\b', 'is_docker_runner', content)
    content = re.sub(r'_substitute_builtin_in_environment\b', '_substitute_builtin_in_runner', content)

    # Replace class names
    content = re.sub(r'\bEnvironment\(', 'Runner(', content)
    content = re.sub(r'class\s+TestEnvironment', 'class TestRunner', content)

    # Replace task.env (but not in quotes/comments about actual env vars)
    content = re.sub(r'task\.env\b', 'task.run_in', content)

    # Replace string literals
    content = re.sub(r'"environments"', '"runners"', content)
    content = re.sub(r"'environments'", "'runners'", content)
    content = re.sub(r'"env"(?!\w)', '"run_in"', content)
    content = re.sub(r"'env'(?!\w)", "'run_in'", content)

    return content

# Find all test Python files
test_files = list(Path('tests').rglob('*.py'))
print(f"Found {len(test_files)} test files")

count = 0
for file_path in test_files:
    try:
        original = file_path.read_text()
        updated = refactor_content(original)

        if updated != original:
            file_path.write_text(updated)
            count += 1
            print(f"Updated {file_path}")
    except Exception as e:
        print(f"Error {file_path}: {e}")

print(f"\nUpdated {count} files")
