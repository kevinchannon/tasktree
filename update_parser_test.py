#!/usr/bin/env python3
import re

file_path = "/home/runner/work/tasktree/tasktree/tests/unit/test_parser.py"

with open(file_path, "r") as f:
    content = f.read()

# Replace YAML key "environments:" with "runners:"
content = re.sub(r"^environments:$", "runners:", content, flags=re.MULTILINE)

# Replace YAML key "env:" with "run_in:" (but not in { env: VAR } context)
content = re.sub(r"(\s+)env:(\s)", r"\1run_in:\2", content)

# Replace Python variable names
content = content.replace("default_env", "default_runner")

# Revert { run_in: to { env: for variable-from-env syntax
content = re.sub(r"\{ run_in:", "{ env:", content)

with open(file_path, "w") as f:
    f.write(content)

print("Updated test_parser.py")
