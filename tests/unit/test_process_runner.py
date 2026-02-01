"""Unit tests for process_runner module."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from tasktree.process_runner import (
    PassthroughProcessRunner,
    ProcessRunner,
    make_process_runner,
)


class TestProcessRunner(unittest.TestCase):
    """Tests for ProcessRunner abstract interface."""

    def test_process_runner_is_abstract(self):
        """ProcessRunner cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            ProcessRunner()

    def test_process_runner_has_run_method(self):
        """ProcessRunner defines run as an abstract method."""
        self.assertTrue(hasattr(ProcessRunner, "run"))
        self.assertTrue(callable(getattr(ProcessRunner, "run")))


class TestPassthroughProcessRunner(unittest.TestCase):
    """Tests for PassthroughProcessRunner implementation."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = PassthroughProcessRunner()

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_calls_subprocess_run_with_positional_args(self, mock_run):
        """run() passes positional arguments to subprocess.run."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_run.return_value = mock_result

        result = self.runner.run(["echo", "test"])

        mock_run.assert_called_once_with(["echo", "test"])
        self.assertEqual(result, mock_result)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_calls_subprocess_run_with_keyword_args(self, mock_run):
        """run() passes keyword arguments to subprocess.run."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_run.return_value = mock_result

        result = self.runner.run(
            ["echo", "test"], check=True, capture_output=True, text=True
        )

        mock_run.assert_called_once_with(
            ["echo", "test"], check=True, capture_output=True, text=True
        )
        self.assertEqual(result, mock_result)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_calls_subprocess_run_with_cwd(self, mock_run):
        """run() passes cwd parameter to subprocess.run."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_run.return_value = mock_result

        result = self.runner.run(["ls"], cwd="/tmp")

        mock_run.assert_called_once_with(["ls"], cwd="/tmp")
        self.assertEqual(result, mock_result)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_calls_subprocess_run_with_env(self, mock_run):
        """run() passes env parameter to subprocess.run."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_run.return_value = mock_result
        env = {"PATH": "/usr/bin", "HOME": "/home/test"}

        result = self.runner.run(["env"], env=env)

        mock_run.assert_called_once_with(["env"], env=env)
        self.assertEqual(result, mock_result)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_calls_subprocess_run_with_stdout_stderr(self, mock_run):
        """run() passes stdout and stderr parameters to subprocess.run."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_run.return_value = mock_result

        result = self.runner.run(
            ["echo", "test"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )

        mock_run.assert_called_once_with(
            ["echo", "test"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self.assertEqual(result, mock_result)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_returns_completed_process(self, mock_run):
        """run() returns subprocess.CompletedProcess from subprocess.run."""
        expected_result = subprocess.CompletedProcess(
            args=["echo", "test"], returncode=0, stdout="test\n", stderr=""
        )
        mock_run.return_value = expected_result

        result = self.runner.run(["echo", "test"])

        self.assertEqual(result, expected_result)
        self.assertIsInstance(result, subprocess.CompletedProcess)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_raises_called_process_error_when_check_true(self, mock_run):
        """run() propagates CalledProcessError when check=True and process fails."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["false"]
        )

        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(["false"], check=True)

        self.assertEqual(context.exception.returncode, 1)
        mock_run.assert_called_once_with(["false"], check=True)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_raises_timeout_expired(self, mock_run):
        """run() propagates TimeoutExpired when timeout is exceeded."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sleep", "10"], timeout=1)

        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(["sleep", "10"], timeout=1)

        mock_run.assert_called_once_with(["sleep", "10"], timeout=1)

    @patch("tasktree.process_runner.subprocess.run")
    def test_run_calls_subprocess_run_with_shell_true(self, mock_run):
        """run() passes shell=True parameter to subprocess.run."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_run.return_value = mock_result

        result = self.runner.run("echo test", shell=True)

        mock_run.assert_called_once_with("echo test", shell=True)
        self.assertEqual(result, mock_result)

    def test_passthrough_runner_is_process_runner(self):
        """PassthroughProcessRunner implements ProcessRunner interface."""
        self.assertIsInstance(self.runner, ProcessRunner)


class TestMakeProcessRunner(unittest.TestCase):
    """Tests for make_process_runner factory function."""

    def test_make_process_runner_returns_process_runner(self):
        """make_process_runner() returns a ProcessRunner instance."""
        runner = make_process_runner()
        self.assertIsInstance(runner, ProcessRunner)

    def test_make_process_runner_returns_passthrough_runner(self):
        """make_process_runner() returns a PassthroughProcessRunner instance."""
        runner = make_process_runner()
        self.assertIsInstance(runner, PassthroughProcessRunner)

    def test_make_process_runner_returns_new_instance_each_call(self):
        """make_process_runner() returns a new instance on each call."""
        runner1 = make_process_runner()
        runner2 = make_process_runner()
        self.assertIsNot(runner1, runner2)


if __name__ == "__main__":
    unittest.main()
