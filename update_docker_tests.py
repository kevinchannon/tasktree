#!/usr/bin/env python3
"""Update test_docker.py to add process_runner parameter to all run_in_container calls."""

import re

# Read the file
with open("tests/unit/test_docker.py", "r") as f:
    content = f.read()

# Pattern to match run_in_container calls without process_runner
# This pattern looks for the call followed by closing parenthesis and newline
pattern = r'(self\.manager\.run_in_container\(\s*env=env,\s*cmd="echo hello",\s*working_dir=Path\("/fake/project"\),\s*container_working_dir="/workspace",\s*)\)'

replacement = r'\1process_runner=mock_runner,\n        )'

# Also need to add mock_runner = MockProcessRunner() before each call
# Pattern: find the Popen mock setup before run_in_container
popen_pattern = r'(mock_popen\.return_value = mock_process\n\n\s+)(self\.manager\.run_in_container\('

popen_replacement = r'\1mock_runner = MockProcessRunner()\n        \2'

# Pattern to change assertion from mock_popen to mock_runner
assertion_pattern1 = r'mock_popen\.assert_called_once\(\)\s*\n\s*run_call_args = mock_popen\.call_args\[0\]\[0\]'
assertion_replacement1 = 'self.assertEqual(len(mock_runner.calls), 1)\n        run_call_args = mock_runner.calls[0][0]'

# Apply replacements
content = re.sub(pattern, replacement, content)
content = re.sub(popen_pattern, popen_replacement, content)
content = re.sub(assertion_pattern1, assertion_replacement1, content)

# Write back
with open("tests/unit/test_docker.py", "w") as f:
    f.write(content)

print("Updated test_docker.py")
