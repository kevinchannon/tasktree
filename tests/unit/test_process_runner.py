"""Unit tests for process_runner module."""

import os
import subprocess
import sys
import unittest
from io import StringIO
from unittest.mock import patch

from helpers.logging import logger_stub
from tasktree.process_runner import (
    StderrOnlyOnFailureProcessRunner,
    PassthroughProcessRunner,
    ProcessRunner,
    SilentProcessRunner,
    StderrOnlyProcessRunner,
    StdoutOnlyProcessRunner,
    TaskOutputTypes,
    make_process_runner,
    stream_output,
)


class TestProcessRunner(unittest.TestCase):
    """
    Tests for ProcessRunner abstract interface.
    """

    def test_process_runner_is_abstract(self):
        """
        ProcessRunner cannot be instantiated directly.
        """
        with self.assertRaises(TypeError):
            ProcessRunner()

    def test_process_runner_has_run_method(self):
        """
        ProcessRunner defines run as an abstract method.
        """
        self.assertTrue(hasattr(ProcessRunner, "run"))
        self.assertTrue(callable(getattr(ProcessRunner, "run")))


class TestPassthroughProcessRunner(unittest.TestCase):
    """
    Tests for PassthroughProcessRunner implementation.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = PassthroughProcessRunner(logger_stub)

    def test_run_executes_command_and_returns_result(self):
        """
        run() executes command and returns CompletedProcess.
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"], capture_output=True, text=True
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "test")

    def test_run_captures_stdout_when_requested(self):
        """
        run() captures stdout when stdout=PIPE is specified.
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('hello')"], stdout=subprocess.PIPE, text=True
        )

        self.assertEqual(result.stdout.strip(), "hello")

    def test_run_captures_stderr_when_requested(self):
        """
        run() captures stderr when stderr=PIPE is specified.
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"],
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.stderr.strip(), "error")

    def test_run_uses_cwd_parameter(self):
        """
        run() executes command in specified working directory.
        """
        test_dir = "/tmp"
        result = self.runner.run(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            cwd=test_dir,
            capture_output=True,
            text=True,
        )

        # Use realpath to handle symlinks (e.g., /tmp -> /private/tmp on macOS)
        self.assertEqual(
            os.path.realpath(result.stdout.strip()), os.path.realpath(test_dir)
        )

    def test_run_uses_env_parameter(self):
        """
        run() passes environment variables to subprocess.
        """
        env = {"TEST_VAR": "test_value"}
        result = self.runner.run(
            [sys.executable, "-c", "import os; print(os.environ.get('TEST_VAR', ''))"],
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "test_value")

    def test_run_returns_completed_process(self):
        """
        run() returns subprocess.CompletedProcess instance.
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"], capture_output=True
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_raises_called_process_error_when_check_true(self):
        """
        run() raises CalledProcessError when check=True and process fails.
        """
        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=True
            )

        self.assertEqual(context.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        run() raises TimeoutExpired when timeout is exceeded.
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
            )

    def test_run_executes_shell_command(self):
        """
        run() executes shell commands when shell=True.
        """
        result = self.runner.run(
            f"{sys.executable} -c \"print('shell test')\"",
            shell=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "shell test")

    def test_passthrough_runner_is_process_runner(self):
        """
        PassthroughProcessRunner implements ProcessRunner interface.
        """
        self.assertIsInstance(self.runner, ProcessRunner)


class TestSilentProcessRunner(unittest.TestCase):
    """
    Tests for SilentProcessRunner implementation.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = SilentProcessRunner(logger_stub)

    def test_run_suppresses_stdout(self):
        """
        run() suppresses stdout output.
        """
        # Run command that produces stdout - output should be suppressed
        result = self.runner.run(
            [sys.executable, "-c", "print('this should not appear')"]
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)
        # stdout should be None (not captured) since we used DEVNULL
        self.assertIsNone(result.stdout)

    def test_run_suppresses_stderr(self):
        """
        run() suppresses stderr output.
        """
        # Run command that produces stderr - output should be suppressed
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"]
        )

        self.assertEqual(result.returncode, 0)
        # stderr should be None (not captured) since we used DEVNULL
        self.assertIsNone(result.stderr)

    def test_run_overrides_stdout_parameter(self):
        """
        run() overrides stdout even if caller specifies stdout=PIPE.
        """
        # Caller tries to capture stdout, but should be overridden to DEVNULL
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"], stdout=subprocess.PIPE, text=True
        )

        # stdout should still be None because DEVNULL overrides PIPE
        self.assertIsNone(result.stdout)

    def test_run_overrides_stderr_parameter(self):
        """
        run() overrides stderr even if caller specifies stderr=PIPE.
        """
        # Caller tries to capture stderr, but should be overridden to DEVNULL
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"],
            stderr=subprocess.PIPE,
            text=True,
        )

        # stderr should still be None because DEVNULL overrides PIPE
        self.assertIsNone(result.stderr)

    def test_run_preserves_other_parameters(self):
        """
        run() preserves other parameters like check, cwd, env.
        """
        env = {"TEST_VAR": "test_value"}

        # This command would print the cwd and env var, but output is suppressed
        result = self.runner.run(
            [
                sys.executable,
                "-c",
                "import os; print(os.getcwd()); print(os.environ.get('TEST_VAR'))",
            ],
            cwd="/tmp",
            env=env,
        )

        # Command should succeed even though output is suppressed
        self.assertEqual(result.returncode, 0)
        # stdout/stderr should be None (suppressed)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)

    def test_run_raises_called_process_error_when_check_true(self):
        """
        run() propagates CalledProcessError when check=True and process fails.
        """
        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=True
            )

        self.assertEqual(context.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        run() propagates TimeoutExpired when timeout is exceeded.
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
            )

    def test_silent_runner_is_process_runner(self):
        """
        SilentProcessRunner implements ProcessRunner interface.
        """
        self.assertIsInstance(self.runner, ProcessRunner)

    def test_run_returns_completed_process(self):
        """
        run() returns subprocess.CompletedProcess instance.
        """
        result = self.runner.run([sys.executable, "-c", "print('test')"])

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_suppresses_both_stdout_and_stderr(self):
        """
        run() suppresses both stdout and stderr simultaneously.
        """
        # Command that writes to both stdout and stderr
        result = self.runner.run(
            [
                sys.executable,
                "-c",
                "import sys; print('stdout'); sys.stderr.write('stderr\\n')",
            ]
        )

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)


class TestStreamOutput(unittest.TestCase):
    def test_stream_output_handles_broken_pipe(self):
        """
        stream_output handles exceptions gracefully (e.g., broken pipe).
        """
        from io import StringIO
        from unittest.mock import Mock

        # Create a mock pipe that raises an exception when read
        mock_pipe = Mock()
        mock_pipe.__iter__ = Mock(side_effect=OSError("Broken pipe"))

        # Create a target that we can verify wasn't written to
        target = StringIO()

        # Call stream_output - should not raise exception
        try:
            stream_output(mock_pipe, target)
            # If we get here without exception, the test passes
            self.assertTrue(True)
        except OSError:
            self.fail("stream_output should handle exceptions gracefully")


class TestStdoutOnlyProcessRunner(unittest.TestCase):
    """
    Tests for StdoutOnlyProcessRunner implementation.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = StdoutOnlyProcessRunner(logger_stub)

    def test_run_forwards_stdout(self):
        """
        run() forwards stdout to sys.stdout.
        """
        # Run a command that produces stdout
        # We can't easily capture the output that goes to sys.stdout from the thread,
        # but we can verify the command executes successfully
        result = self.runner.run([sys.executable, "-c", "print('test stdout')"])

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)
        # stdout should be None since we streamed it
        self.assertIsNone(result.stdout)

    def test_run_suppresses_stderr(self):
        """
        run() suppresses stderr output.
        """
        # Run command that produces stderr - output should be suppressed
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"]
        )

        self.assertEqual(result.returncode, 0)
        # stderr should be None (suppressed)
        self.assertIsNone(result.stderr)

    def test_run_handles_both_stdout_and_stderr(self):
        """
        run() forwards stdout while suppressing stderr.
        """
        # Command that writes to both stdout and stderr
        result = self.runner.run(
            [
                sys.executable,
                "-c",
                "import sys; print('stdout'); sys.stderr.write('stderr\\n')",
            ]
        )

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)

    def test_run_raises_called_process_error_when_check_true(self):
        """
        run() raises CalledProcessError when check=True and process fails.
        """
        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=True
            )

        self.assertEqual(context.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        run() raises TimeoutExpired when timeout is exceeded.
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
            )

    def test_stdout_only_runner_is_process_runner(self):
        """
        StdoutOnlyProcessRunner implements ProcessRunner interface.
        """
        self.assertIsInstance(self.runner, ProcessRunner)

    def test_run_returns_completed_process(self):
        """
        run() returns subprocess.CompletedProcess instance.
        """
        result = self.runner.run([sys.executable, "-c", "print('test')"])

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_preserves_exit_code(self):
        """
        run() preserves non-zero exit codes.
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.exit(42)"], check=False
        )

        self.assertEqual(result.returncode, 42)


class TestStderrOnlyProcessRunner(unittest.TestCase):
    """
    Tests for StderrOnlyProcessRunner implementation.
    """

    def setUp(self):
        """
        Set up test fixtures.
        """
        self.runner = StderrOnlyProcessRunner(logger_stub)

    def test_run_forwards_stderr(self):
        """
        run() forwards stderr to sys.stderr.
        """
        # Run a command that produces stderr
        # We can't easily capture the output that goes to sys.stderr from the thread,
        # but we can verify the command executes successfully
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('test stderr\\n')"]
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)
        # stderr should be None since we streamed it
        self.assertIsNone(result.stderr)

    def test_run_suppresses_stdout(self):
        """
        run() suppresses stdout output.
        """
        # Run command that produces stdout - output should be suppressed
        result = self.runner.run([sys.executable, "-c", "print('test output')"])

        self.assertEqual(result.returncode, 0)
        # stdout should be None (suppressed)
        self.assertIsNone(result.stdout)

    def test_run_handles_both_stdout_and_stderr(self):
        """
        run() forwards stderr while suppressing stdout.
        """
        # Command that writes to both stdout and stderr
        result = self.runner.run(
            [
                sys.executable,
                "-c",
                "import sys; print('stdout'); sys.stderr.write('stderr\\n')",
            ]
        )

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)

    def test_run_raises_called_process_error_when_check_true(self):
        """
        run() raises CalledProcessError when check=True and process fails.
        """
        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=True
            )

        self.assertEqual(context.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        run() raises TimeoutExpired when timeout is exceeded.
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
            )

    def test_stderr_only_runner_is_process_runner(self):
        """
        StderrOnlyProcessRunner implements ProcessRunner interface.
        """
        self.assertIsInstance(self.runner, ProcessRunner)

    def test_run_returns_completed_process(self):
        """
        run() returns subprocess.CompletedProcess instance.
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('test\\n')"]
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_preserves_exit_code(self):
        """
        run() preserves non-zero exit codes.
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.exit(42)"], check=False
        )

        self.assertEqual(result.returncode, 42)


class TestStderrOnlyOnFailureProcessRunner(unittest.TestCase):
    """
    Tests for StderrOnlyOnFailureProcessRunner implementation.
    """

    def setUp(self):
        self.runner = StderrOnlyOnFailureProcessRunner(logger_stub)

    def test_run_suppresses_stderr_on_success(self):
        """
        StderrOnlyOnFailureProcessRunner buffers stderr but does not output it on success.
        """
        stderr_capture = StringIO()

        with patch("sys.stderr", stderr_capture):
            result = self.runner.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('error message\\n'); sys.exit(0)",
                ],
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        # Stderr should NOT be output since process succeeded
        self.assertEqual(stderr_capture.getvalue(), "")

    def test_run_outputs_buffered_stderr_on_failure(self):
        """
        StderrOnlyOnFailureProcessRunner outputs buffered stderr when process fails.
        """
        stderr_capture = StringIO()

        with patch("sys.stderr", stderr_capture):
            result = self.runner.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('error message\\n'); sys.exit(1)",
                ],
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        # Stderr SHOULD be output since process failed
        self.assertIn("error message", stderr_capture.getvalue())

    def test_run_handles_failure_with_no_stderr(self):
        """
        StderrOnlyOnFailureProcessRunner handles process failure with no stderr output.
        """
        stderr_capture = StringIO()

        with patch("sys.stderr", stderr_capture):
            result = self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=False
            )

        self.assertEqual(result.returncode, 1)
        # No stderr to output
        self.assertEqual(stderr_capture.getvalue(), "")

    def test_run_handles_success_with_no_output(self):
        """
        StderrOnlyOnFailureProcessRunner handles successful process with no output.
        """
        stderr_capture = StringIO()

        with patch("sys.stderr", stderr_capture):
            result = self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(0)"], check=False
            )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(stderr_capture.getvalue(), "")

    def test_run_ignores_stdout_completely(self):
        """
        StderrOnlyOnFailureProcessRunner sends stdout to DEVNULL.
        """
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        with patch("sys.stdout", stdout_capture), patch("sys.stderr", stderr_capture):
            result = self.runner.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stdout.write('stdout message\\n'); sys.stderr.write('stderr message\\n'); sys.exit(1)",
                ],
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        # Stdout should be completely ignored
        self.assertEqual(stdout_capture.getvalue(), "")
        # Stderr should be output because process failed
        self.assertIn("stderr message", stderr_capture.getvalue())

    def test_run_raises_called_process_error_when_check_true(self):
        """
        StderrOnlyOnFailureProcessRunner raises CalledProcessError when check=True and process fails.
        """
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"], check=True
            )

        self.assertEqual(cm.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        StderrOnlyOnFailureProcessRunner raises TimeoutExpired when timeout is exceeded.
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
            )

    def test_stderr_only_on_failure_runner_is_process_runner(self):
        """
        StderrOnlyOnFailureProcessRunner is an instance of ProcessRunner.
        """
        self.assertIsInstance(self.runner, ProcessRunner)

    def test_run_returns_completed_process(self):
        """
        StderrOnlyOnFailureProcessRunner.run() returns CompletedProcess object.
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.exit(0)"], check=False
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_preserves_exit_code(self):
        """
        StderrOnlyOnFailureProcessRunner preserves the process exit code.
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.exit(42)"], check=False
        )

        self.assertEqual(result.returncode, 42)

    def test_run_handles_multiple_stderr_lines(self):
        """
        StderrOnlyOnFailureProcessRunner correctly buffers and outputs multiple stderr lines.
        """
        stderr_capture = StringIO()

        with patch("sys.stderr", stderr_capture):
            result = self.runner.run(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('line1\\n'); sys.stderr.write('line2\\n'); sys.stderr.write('line3\\n'); sys.exit(1)",
                ],
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        stderr_output = stderr_capture.getvalue()
        self.assertIn("line1", stderr_output)
        self.assertIn("line2", stderr_output)
        self.assertIn("line3", stderr_output)


class TestMakeProcessRunner(unittest.TestCase):
    """
    Tests for make_process_runner factory function.
    """

    def test_make_process_runner_with_all_returns_passthrough(self):
        """
        make_process_runner(TaskOutputTypes.ALL) returns PassthroughProcessRunner.
        """
        runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.assertIsInstance(runner, PassthroughProcessRunner)

    def test_make_process_runner_with_none_returns_silent(self):
        """
        make_process_runner(TaskOutputTypes.NONE) returns SilentProcessRunner.
        """
        runner = make_process_runner(TaskOutputTypes.NONE, logger_stub)
        self.assertIsInstance(runner, SilentProcessRunner)

    def test_make_process_runner_with_out_returns_stdout_only(self):
        """
        make_process_runner(TaskOutputTypes.OUT) returns StdoutOnlyProcessRunner.
        """
        runner = make_process_runner(TaskOutputTypes.OUT, logger_stub)
        self.assertIsInstance(runner, StdoutOnlyProcessRunner)

    def test_make_process_runner_with_err_returns_stderr_only(self):
        """
        make_process_runner(TaskOutputTypes.ERR) returns StderrOnlyProcessRunner.
        """
        runner = make_process_runner(TaskOutputTypes.ERR, logger_stub)
        self.assertIsInstance(runner, StderrOnlyProcessRunner)

    def test_make_process_runner_with_on_err_returns_stderr_only_on_failure(self):
        """
        make_process_runner(TaskOutputTypes.ON_ERR) returns StderrOnlyOnFailureProcessRunner.
        """
        runner = make_process_runner(TaskOutputTypes.ON_ERR, logger_stub)
        self.assertIsInstance(runner, StderrOnlyOnFailureProcessRunner)

    def test_make_process_runner_with_invalid_raises_error(self):
        """
        make_process_runner() raises ValueError for invalid TaskOutputTypes.
        """
        # Create an invalid enum value by casting
        invalid_value = "invalid"
        with self.assertRaises(ValueError) as cm:
            # We can't create an invalid enum value directly, so we'll test
            # by creating a string that would fail enum validation
            make_process_runner(invalid_value, logger_stub)  # type: ignore

        self.assertIn("Invalid TaskOutputTypes", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
