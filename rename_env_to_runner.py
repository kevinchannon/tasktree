#!/usr/bin/env python3
"""
Script to rename environment/env to runner/run_in throughout the codebase.
This is a large refactoring for issue #64.
"""

import re
from pathlib import Path

def replace_in_file(filepath: Path, replacements: list[tuple[str, str]]) -> bool:
    """Apply replacements to a file. Returns True if file was modified."""
    try:
        content = filepath.read_text()
        original = content

        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)

        if content != original:
            filepath.write_text(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    # Define replacements (order matters!)
    python_replacements = [
        # Class name
        (r'\bclass Environment:', r'class Runner:'),
        # Type hints
        (r'dict\[str, Environment\]', r'dict[str, Runner]'),
        (r'\) -> Environment \|', r') -> Runner |'),
        (r'\) -> Environment\b', r') -> Runner'),
        # Instantiation
        (r' Environment\(', r' Runner('),
        # Dictionary field name
        (r'\benvironments:', r'runners:'),
        (r'\.environments\b', r'.runners'),
        (r'\benvironments\s*=', r'runners ='),
        # Method names
        (r'def get_environment\(', r'def get_runner('),
        (r'get_environment\(', r'get_runner('),
        # Task field (more specific to avoid env vars)
        (r'(\s+)env: str = ""', r'\1run_in: str = ""'),
        (r'task\.env\b', r'task.run_in'),
        # Comments about Environment (preserve "environment variable" though)
        (r'# Environment name', r'# Runner name'),
        (r'shell environment', r'shell runner'),
        (r'Docker environment', r'Docker runner'),
        (r'execution environment', r'execution runner'),
        # String literals for YAML keys
        (r'"environments"', r'"runners"'),
        (r"'environments'", r"'runners'"),
        (r'"env"(?=\s*[:)])', r'"run_in"'),  # Only replace "env" when followed by : or )
    ]

    yaml_replacements = [
        (r'\benvironments:', r'runners:'),
        (r'\benv:', r'run_in:'),
    ]

    markdown_replacements = [
        (r'\benvironments:', r'runners:'),
        (r'`environments`', r'`runners`'),
        (r'tasks\.<name>\.env', r'tasks.<name>.run_in'),
        (r'\.env:', r'.run_in:'),
        (r'\benv:', r'run_in:'),
        (r'environment definition', r'runner definition'),
        (r'Environment definition', r'Runner definition'),
        (r'execution environment', r'execution runner'),
    ]

    json_replacements = [
        (r'"environments"', r'"runners"'),
        (r'"env"', r'"run_in"'),
    ]

    # Process Python files
    print("Processing Python files...")
    py_files = list(Path('.').rglob('*.py'))
    py_files = [f for f in py_files if '.venv' not in str(f) and '__pycache__' not in str(f)]

    modified_py = []
    for filepath in py_files:
        if replace_in_file(filepath, python_replacements):
            modified_py.append(str(filepath))
            print(f"  Modified: {filepath}")

    # Process YAML files
    print("\nProcessing YAML files...")
    yaml_files = list(Path('.').rglob('*.yaml')) + list(Path('.').rglob('*.yml'))
    yaml_files = [f for f in yaml_files if '.venv' not in str(f)]

    modified_yaml = []
    for filepath in yaml_files:
        if replace_in_file(filepath, yaml_replacements):
            modified_yaml.append(str(filepath))
            print(f"  Modified: {filepath}")

    # Process Markdown files
    print("\nProcessing Markdown files...")
    md_files = list(Path('.').rglob('*.md'))
    md_files = [f for f in md_files if '.venv' not in str(f)]

    modified_md = []
    for filepath in md_files:
        if replace_in_file(filepath, markdown_replacements):
            modified_md.append(str(filepath))
            print(f"  Modified: {filepath}")

    # Process JSON files (schema)
    print("\nProcessing JSON files...")
    json_files = list(Path('.').rglob('*.json'))
    json_files = [f for f in json_files if '.venv' not in str(f) and 'node_modules' not in str(f)]

    modified_json = []
    for filepath in json_files:
        if replace_in_file(filepath, json_replacements):
            modified_json.append(str(filepath))
            print(f"  Modified: {filepath}")

    print(f"\n\nSummary:")
    print(f"  Python files modified: {len(modified_py)}")
    print(f"  YAML files modified: {len(modified_yaml)}")
    print(f"  Markdown files modified: {len(modified_md)}")
    print(f"  JSON files modified: {len(modified_json)}")
    print(f"  Total files modified: {len(modified_py) + len(modified_yaml) + len(modified_md) + len(modified_json)}")

if __name__ == '__main__':
    main()
