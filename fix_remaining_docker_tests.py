#!/usr/bin/env python3
"""Fix remaining docker test mocks."""

from pathlib import Path

test_file = Path("tests/unit/test_docker.py")
content = test_file.read_text()

# Pattern for remaining tests
replacements = [
    # test_run_in_container_includes_extra_args
    (
        '''    @patch("tasktree.docker.subprocess.Popen")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_includes_extra_args(self, mock_platform, mock_run):''',
        '''    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.subprocess.Popen")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_includes_extra_args(self, mock_platform, mock_popen, mock_subprocess_run):'''
    ),
    # test_run_in_container_with_empty_extra_args
    (
        '''    @patch("tasktree.docker.subprocess.Popen")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_empty_extra_args(self, mock_platform, mock_run):''',
        '''    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.subprocess.Popen")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_empty_extra_args(self, mock_platform, mock_popen, mock_subprocess_run):'''
    ),
    # test_run_in_container_with_shell_args
    (
        '''    @patch("tasktree.docker.subprocess.Popen")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_shell_args(self, mock_platform, mock_run):''',
        '''    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.subprocess.Popen")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_shell_args(self, mock_platform, mock_popen, mock_subprocess_run):'''
    ),
    # test_run_in_container_with_substituted_variables_in_volumes
    (
        '''    @patch("tasktree.docker.subprocess.Popen")
    def test_run_in_container_with_substituted_variables_in_volumes(self, mock_run):''',
        '''    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.subprocess.Popen")
    def test_run_in_container_with_substituted_variables_in_volumes(self, mock_popen, mock_subprocess_run):'''
    ),
]

for old, new in replacements:
    content = content.replace(old, new)

# Replace mock_run.side_effect with mock_subprocess_run.side_effect for these tests
content = content.replace(
    "        mock_run.side_effect = mock_run_side_effect",
    """        mock_subprocess_run.side_effect = mock_run_side_effect

        # Mock subprocess.Popen for docker run
        mock_process = Mock()
        mock_process.wait.return_value = 0
        mock_process.stdout = None
        mock_process.stderr = None
        mock_popen.return_value = mock_process"""
)

# Replace mock_run.call_args_list[3][0][0] with mock_popen.call_args[0][0]
content = content.replace(
    "run_call_args = mock_run.call_args_list[3][0][0]",
    """mock_popen.assert_called_once()
        run_call_args = mock_popen.call_args[0][0]"""
)

test_file.write_text(content)
print("Fixed remaining docker tests!")
