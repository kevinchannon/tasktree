#!/usr/bin/env python3
"""Fix subprocess mocks in unit tests - change from subprocess.run to subprocess.Popen."""

import re
from pathlib import Path

def fix_executor_tests():
    """Fix tests/unit/test_executor.py"""
    test_file = Path("tests/unit/test_executor.py")
    content = test_file.read_text()

    # Replace @patch decorator
    content = content.replace('@patch("subprocess.run")', '@patch("subprocess.Popen")')

    # Replace mock_run.return_value patterns for simple cases
    # Pattern: mock_run.return_value = MagicMock(returncode=X)
    # Replace with mock that has wait() method and optional stdout/stderr
    content = re.sub(
        r'mock_run\.return_value = MagicMock\(returncode=(\d+)\)',
        lambda m: f'mock_process = MagicMock()\n        mock_process.wait.return_value = {m.group(1)}\n        mock_process.stdout = None\n        mock_process.stderr = None\n        mock_run.return_value = mock_process',
        content
    )

    test_file.write_text(content)
    print(f"Fixed {test_file}")

def fix_docker_tests():
    """Fix tests/unit/test_docker.py"""
    test_file = Path("tests/unit/test_docker.py")
    content = test_file.read_text()

    # Replace @patch decorator (with module prefix)
    content = content.replace('@patch("tasktree.docker.subprocess.run")', '@patch("tasktree.docker.subprocess.Popen")')

    # These tests might have different patterns - let's check
    test_file.write_text(content)
    print(f"Fixed {test_file}")

if __name__ == "__main__":
    fix_executor_tests()
    fix_docker_tests()
    print("Done!")
