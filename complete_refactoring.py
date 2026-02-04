#!/usr/bin/env python3
"""
Complete the environment → runner refactoring for test and documentation files.

This script updates:
1. All test files (*.py in tests/)
2. Documentation files (README.md, CLAUDE.md, schema/README.md)
3. Schema file (schema/tasktree-schema.json)

Run this after the source code has been refactored.
"""

import json
import re
from pathlib import Path
from typing import Callable


def refactor_python_content(content: str) -> str:
    """Apply refactoring rules to Python test files."""

    # 1. Replace imports
    content = re.sub(
        r"from tasktree\.parser import ([^\n]*\bEnvironment\b[^\n]*)",
        lambda m: m.group(0).replace("Environment", "Runner"),
        content,
    )

    # 2. Replace type hints
    content = re.sub(r":\s*Environment(?=\s|,|\)|\]|$)", ": Runner", content)
    content = re.sub(r"dict\[str,\s*Environment\]", "dict[str, Runner]", content)
    content = re.sub(r"Optional\[Environment\]", "Optional[Runner]", content)

    # 3. Replace YAML field names in strings (preserve indentation)
    content = re.sub(
        r"^(\s*)environments:(\s*)$", r"\1runners:\2", content, flags=re.MULTILINE
    )
    content = re.sub(r"^(\s+)env:(\s+)", r"\1run_in:\2", content, flags=re.MULTILINE)

    # 4. Replace method calls
    content = re.sub(r"\.get_environment\(", ".get_runner(", content)
    content = re.sub(r"\.environments\b", ".runners", content)

    # 5. Replace function names
    content = re.sub(
        r"\bhash_environment_definition\b", "hash_runner_definition", content
    )
    content = re.sub(r"\bis_docker_environment\b", "is_docker_runner", content)
    content = re.sub(
        r"_substitute_builtin_in_environment\b",
        "_substitute_builtin_in_runner",
        content,
    )

    # 6. Replace class names
    content = re.sub(r"\bEnvironment\(", "Runner(", content)
    content = re.sub(r"class\s+TestEnvironment(\w*)", r"class TestRunner\1", content)

    # 7. Replace task.env attribute access
    content = re.sub(r"task\.env\b", "task.run_in", content)
    content = re.sub(r"self\.env\b", "self.run_in", content)

    # 8. Replace string literals (but NOT "environment variable")
    content = re.sub(r'"environments"', '"runners"', content)
    content = re.sub(r"'environments'", "'runners'", content)
    # Be careful with "env" - only replace in specific contexts
    content = re.sub(r'\.get\("env",', '.get("run_in",', content)
    content = re.sub(r'\["env"\]', '["run_in"]', content)
    content = re.sub(r'task_data\.get\("env"', 'task_data.get("run_in"', content)

    # 9. Replace comments (but not "environment variable")
    content = re.sub(
        r"# .*\benvironment definition\b",
        lambda m: m.group(0).replace("environment definition", "runner definition"),
        content,
    )
    content = re.sub(
        r"# .*\bDocker environment\b",
        lambda m: m.group(0).replace("Docker environment", "Docker runner"),
        content,
    )

    return content


def refactor_markdown_content(content: str) -> str:
    """Apply refactoring rules to Markdown documentation files."""

    # Replace code blocks with environments:
    content = re.sub(
        r"(```yaml\n(?:.*\n)*?)environments:",
        r"\1runners:",
        content,
        flags=re.MULTILINE,
    )

    # Replace env: in YAML code blocks
    content = re.sub(
        r"(```yaml\n(?:.*\n)*?(?:\s+))env:", r"\1run_in:", content, flags=re.MULTILINE
    )

    # Replace in prose (but not "environment variable")
    content = re.sub(r"\benvironments section\b", "runners section", content)
    content = re.sub(r"\benvironments are\b", "runners are", content)
    content = re.sub(r"\benvironment is\b", "runner is", content)
    content = re.sub(r"\benvironment name\b", "runner name", content)
    content = re.sub(r"\benvironment definition\b", "runner definition", content)
    content = re.sub(r"\bDocker environment\b", "Docker runner", content)
    content = re.sub(r"\bshell environment\b", "shell runner", content)
    content = re.sub(r"\bexecution environment\b", "execution runner", content)
    content = re.sub(r"\bcustom environment\b", "custom runner", content)
    content = re.sub(r"\bdefault environment\b", "default runner", content)

    # Replace CLI flags
    content = re.sub(r"--env\b", "--run-in", content)
    content = re.sub(r"`env`", "`run_in`", content)

    # Replace field references
    content = re.sub(r"task\'s `env` field", "task's `run_in` field", content)
    content = re.sub(r"`env` field", "`run_in` field", content)

    # Replace class names
    content = re.sub(r"\bEnvironment\b(?!al variable)", "Runner", content)

    return content


def refactor_json_schema(content: str) -> str:
    """Apply refactoring rules to JSON schema file."""
    schema = json.loads(content)

    # Update top-level properties
    if "properties" in schema:
        if "environments" in schema["properties"]:
            schema["properties"]["runners"] = schema["properties"].pop("environments")

        # Update task properties
        if "tasks" in schema["properties"]:
            task_def = schema["properties"]["tasks"]
            if "patternProperties" in task_def:
                for pattern, task_schema in task_def["patternProperties"].items():
                    if "properties" in task_schema:
                        if "env" in task_schema["properties"]:
                            task_schema["properties"]["run_in"] = task_schema[
                                "properties"
                            ].pop("env")

    # Update definitions
    if "definitions" in schema or "$defs" in schema:
        defs = schema.get("definitions", schema.get("$defs", {}))

        if "Environment" in defs:
            defs["Runner"] = defs.pop("Environment")

        # Update references
        def update_refs(obj):
            if isinstance(obj, dict):
                if "$ref" in obj and "Environment" in obj["$ref"]:
                    obj["$ref"] = obj["$ref"].replace("Environment", "Runner")
                for value in obj.values():
                    update_refs(value)
            elif isinstance(obj, list):
                for item in obj:
                    update_refs(item)

        update_refs(schema)

    return json.dumps(schema, indent=2)


def process_file(file_path: Path, refactor_fn: Callable[[str], str]) -> bool:
    """Process a single file with the given refactor function."""
    try:
        original = file_path.read_text(encoding="utf-8")
        updated = refactor_fn(original)

        if updated != original:
            file_path.write_text(updated, encoding="utf-8")
            return True
        return False
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        raise


def main():
    """Main refactoring entry point."""
    root = Path(".")

    stats = {
        "tests": 0,
        "docs": 0,
        "schema": 0,
    }

    print("🔄 Starting refactoring...\n")

    # 1. Process test files
    print("📝 Processing test files...")
    for py_file in (root / "tests").rglob("*.py"):
        if process_file(py_file, refactor_python_content):
            stats["tests"] += 1
            print(f"  ✓ {py_file}")

    # 2. Process documentation files
    print("\n📚 Processing documentation files...")
    doc_files = ["README.md", "CLAUDE.md", "schema/README.md"]
    for doc_file in doc_files:
        doc_path = root / doc_file
        if doc_path.exists():
            if process_file(doc_path, refactor_markdown_content):
                stats["docs"] += 1
                print(f"  ✓ {doc_path}")

    # 3. Process schema file
    print("\n🔧 Processing schema file...")
    schema_path = root / "schema" / "tasktree-schema.json"
    if schema_path.exists():
        if process_file(schema_path, refactor_json_schema):
            stats["schema"] += 1
            print(f"  ✓ {schema_path}")

    # Summary
    print("\n" + "=" * 60)
    print("✅ Refactoring complete!")
    print(f"  Test files updated:   {stats['tests']}")
    print(f"  Doc files updated:    {stats['docs']}")
    print(f"  Schema files updated: {stats['schema']}")
    print("=" * 60)

    print("\n🧪 Next steps:")
    print("  1. Run tests: pytest tests/")
    print("  2. Review changes: git diff")
    print(
        "  3. Commit: git add -A && git commit -m 'Complete environment → runner refactoring'"
    )


if __name__ == "__main__":
    main()
