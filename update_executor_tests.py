#!/usr/bin/env python3
"""
Script to update test_executor.py to use ProcessRunner mocks instead of subprocess.Popen.
"""

import re
from pathlib import Path

def update_test_file():
    """Update test_executor.py to use ProcessRunner mocking."""
    test_file = Path("tests/unit/test_executor.py")
    content = test_file.read_text()

    # Pattern to find test methods with subprocess.Popen patches
    # Match: @patch("subprocess.Popen") followed optionally by other patches, then the method

    # Remove @patch("subprocess.Popen") decorators
    content = re.sub(
        r'    @patch\("subprocess\.Popen"\)\n',
        '',
        content
    )

    # Remove mock_run parameters from test methods that have them
    # Pattern: def test_name(self, ..., mock_run)
    content = re.sub(
        r'(def test_\w+\(self(?:, [^)]*?)?), mock_run\)',
        r'\1)',
        content
    )

    # Replace mock_process setup with ProcessRunner factory
    # Find and replace the pattern:
    #   mock_process = MagicMock()
    #   mock_process.wait.return_value = 0
    #   mock_process.stdout = None
    #   mock_process.stderr = None
    #   mock_run.return_value = mock_process

    # Note: This is complex, so we'll do targeted replacements

    # Replace executor initialization to use mock factory
    # Pattern: executor = Executor(recipe, state_manager, logger_stub)
    # Replace with: executor = Executor(recipe, state_manager, logger_stub, process_runner_factory=make_mock_process_runner_factory(exit_code=0))

    # But only for tests that previously had mock_run
    # This is tricky - let's do a manual approach for the key tests

    # For now, just write the modified content
    test_file.write_text(content)
    print(f"Updated {test_file}")
    print("Note: Manual review required for executor initialization updates")

if __name__ == "__main__":
    update_test_file()
