#!/usr/bin/env python3
"""
Script to refactor test files from environment → runner terminology.
"""

import re
import sys
from pathlib import Path


def refactor_file(file_path: Path) -> None:
    """Refactor a single file."""
    content = file_path.read_text()
    original = content

    # Replace class imports
    content = re.sub(
        r"\bfrom tasktree\.parser import.*\bEnvironment\b",
        lambda m: m.group(0).replace("Environment", "Runner"),
        content,
    )

    # Replace class type hints (but not in "environment variable" contexts)
    content = re.sub(r":\s*Environment\b(?!\s+variable)", ": Runner", content)
    content = re.sub(r"Environment\[", "Runner[", content)
    content = re.sub(r"dict\[str,\s*Environment\]", "dict[str, Runner]", content)

    # Replace YAML field names
    content = re.sub(
        r"^\s*environments:\s*$",
        lambda m: m.group(0).replace("environments:", "runners:"),
        content,
        flags=re.MULTILINE,
    )
    content = re.sub(r"(\s+)env:\s+", r"\1run_in: ", content)

    # Replace method calls
    content = re.sub(r"\.get_environment\(", ".get_runner(", content)
    content = re.sub(r"recipe\.environments\b", "recipe.runners", content)
    content = re.sub(r"self\.environments\b", "self.runners", content)

    # Replace function names
    content = re.sub(
        r"\bhash_environment_definition\b", "hash_runner_definition", content
    )
    content = re.sub(r"\bis_docker_environment\b", "is_docker_runner", content)
    content = re.sub(
        r"_substitute_builtin_in_environment\b",
        "_substitute_builtin_in_runner",
        content,
    )

    # Replace task.env references
    content = re.sub(r"\.env\b(?!\s*=|\s*:)", ".run_in", content)
    content = re.sub(r"task\.env\s*=", "task.run_in =", content)

    # Replace Environment() constructor calls
    content = re.sub(r"\bEnvironment\(", "Runner(", content)

    # Replace "environment" in strings/comments (carefully)
    # Only in specific contexts, not "environment variable"
    content = re.sub(r'"environments"', '"runners"', content)
    content = re.sub(r"'environments'", "'runners'", content)

    # Update docstrings and comments
    content = re.sub(
        r"# .*environment definition",
        lambda m: m.group(0).replace("environment definition", "runner definition"),
        content,
    )
    content = re.sub(
        r"# .*Environment definition",
        lambda m: m.group(0).replace("Environment definition", "Runner definition"),
        content,
    )
    content = re.sub(
        r"# .*Docker environment",
        lambda m: m.group(0).replace("Docker environment", "Docker runner"),
        content,
    )

    if content != original:
        file_path.write_text(content)
        print(f"Updated: {file_path}")
    else:
        print(f"No changes: {file_path}")


def main():
    tests_dir = Path("tests")

    if not tests_dir.exists():
        print("tests directory not found")
        sys.exit(1)

    # Process all Python files in tests/
    for py_file in tests_dir.rglob("*.py"):
        try:
            refactor_file(py_file)
        except Exception as e:
            print(f"Error processing {py_file}: {e}")
            sys.exit(1)

    print("\nRefactoring complete!")


if __name__ == "__main__":
    main()
