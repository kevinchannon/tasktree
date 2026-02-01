"""Unit tests for process_runner module."""

import os
import subprocess
import sys
import unittest

from tasktree.process_runner import (
    PassthroughProcessRunner,
    ProcessRunner,
    SilentProcessRunner,
    TaskOutputTypes,
    make_process_runner,
)


class TestProcessRunner(unittest.TestCase):
    """
    Tests for ProcessRunner abstract interface.
    @athena: 2bff092195e6
    """

    def test_process_runner_is_abstract(self):
        """
        ProcessRunner cannot be instantiated directly.
        @athena: daac65da93e2
        """
        with self.assertRaises(TypeError):
            ProcessRunner()

    def test_process_runner_has_run_method(self):
        """
        ProcessRunner defines run as an abstract method.
        @athena: 93aee4ee423d
        """
        self.assertTrue(hasattr(ProcessRunner, "run"))
        self.assertTrue(callable(getattr(ProcessRunner, "run")))


class TestPassthroughProcessRunner(unittest.TestCase):
    """
    Tests for PassthroughProcessRunner implementation.
    @athena: 23c89ef36346
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 61cd9d62c968
        """
        self.runner = PassthroughProcessRunner()

    def test_run_executes_command_and_returns_result(self):
        """
        run() executes command and returns CompletedProcess.
        @athena: fdbd1736580a
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"],
            capture_output=True,
            text=True
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "test")

    def test_run_captures_stdout_when_requested(self):
        """
        run() captures stdout when stdout=PIPE is specified.
        @athena: 273fec922ecb
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('hello')"],
            stdout=subprocess.PIPE,
            text=True
        )

        self.assertEqual(result.stdout.strip(), "hello")

    def test_run_captures_stderr_when_requested(self):
        """
        run() captures stderr when stderr=PIPE is specified.
        @athena: e41a18e7158b
        """
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"],
            stderr=subprocess.PIPE,
            text=True
        )

        self.assertEqual(result.stderr.strip(), "error")

    def test_run_uses_cwd_parameter(self):
        """
        run() executes command in specified working directory.
        @athena: 70d97cb42a40
        """
        test_dir = "/tmp"
        result = self.runner.run(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            cwd=test_dir,
            capture_output=True,
            text=True
        )

        # Use realpath to handle symlinks (e.g., /tmp -> /private/tmp on macOS)
        self.assertEqual(
            os.path.realpath(result.stdout.strip()),
            os.path.realpath(test_dir)
        )

    def test_run_uses_env_parameter(self):
        """
        run() passes environment variables to subprocess.
        @athena: a4c3d81350b2
        """
        env = {"TEST_VAR": "test_value"}
        result = self.runner.run(
            [sys.executable, "-c", "import os; print(os.environ.get('TEST_VAR', ''))"],
            env=env,
            capture_output=True,
            text=True
        )

        self.assertEqual(result.stdout.strip(), "test_value")

    def test_run_returns_completed_process(self):
        """
        run() returns subprocess.CompletedProcess instance.
        @athena: 9869c9cb26a3
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"],
            capture_output=True
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_raises_called_process_error_when_check_true(self):
        """
        run() raises CalledProcessError when check=True and process fails.
        @athena: bfe001d890b9
        """
        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"],
                check=True
            )

        self.assertEqual(context.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        run() raises TimeoutExpired when timeout is exceeded.
        @athena: d00a1b51cec2
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.1
            )

    def test_run_executes_shell_command(self):
        """
        run() executes shell commands when shell=True.
        @athena: 3d0b2b764077
        """
        result = self.runner.run(
            f"{sys.executable} -c \"print('shell test')\"",
            shell=True,
            capture_output=True,
            text=True
        )

        self.assertEqual(result.stdout.strip(), "shell test")

    def test_passthrough_runner_is_process_runner(self):
        """
        PassthroughProcessRunner implements ProcessRunner interface.
        @athena: 8eb7b69f432a
        """
        self.assertIsInstance(self.runner, ProcessRunner)


class TestSilentProcessRunner(unittest.TestCase):
    """
    Tests for SilentProcessRunner implementation.
    @athena: TBD
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: TBD
        """
        self.runner = SilentProcessRunner()

    def test_run_suppresses_stdout(self):
        """
        run() suppresses stdout output.
        @athena: TBD
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
        @athena: TBD
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
        @athena: TBD
        """
        # Caller tries to capture stdout, but should be overridden to DEVNULL
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"],
            stdout=subprocess.PIPE,
            text=True
        )

        # stdout should still be None because DEVNULL overrides PIPE
        self.assertIsNone(result.stdout)

    def test_run_overrides_stderr_parameter(self):
        """
        run() overrides stderr even if caller specifies stderr=PIPE.
        @athena: TBD
        """
        # Caller tries to capture stderr, but should be overridden to DEVNULL
        result = self.runner.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('error\\n')"],
            stderr=subprocess.PIPE,
            text=True
        )

        # stderr should still be None because DEVNULL overrides PIPE
        self.assertIsNone(result.stderr)

    def test_run_preserves_other_parameters(self):
        """
        run() preserves other parameters like check, cwd, env.
        @athena: TBD
        """
        env = {"TEST_VAR": "test_value"}

        # This command would print the cwd and env var, but output is suppressed
        result = self.runner.run(
            [sys.executable, "-c", "import os; print(os.getcwd()); print(os.environ.get('TEST_VAR'))"],
            cwd="/tmp",
            env=env
        )

        # Command should succeed even though output is suppressed
        self.assertEqual(result.returncode, 0)
        # stdout/stderr should be None (suppressed)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)

    def test_run_raises_called_process_error_when_check_true(self):
        """
        run() propagates CalledProcessError when check=True and process fails.
        @athena: TBD
        """
        with self.assertRaises(subprocess.CalledProcessError) as context:
            self.runner.run(
                [sys.executable, "-c", "import sys; sys.exit(1)"],
                check=True
            )

        self.assertEqual(context.exception.returncode, 1)

    def test_run_raises_timeout_expired(self):
        """
        run() propagates TimeoutExpired when timeout is exceeded.
        @athena: TBD
        """
        with self.assertRaises(subprocess.TimeoutExpired):
            self.runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.1
            )

    def test_silent_runner_is_process_runner(self):
        """
        SilentProcessRunner implements ProcessRunner interface.
        @athena: TBD
        """
        self.assertIsInstance(self.runner, ProcessRunner)

    def test_run_returns_completed_process(self):
        """
        run() returns subprocess.CompletedProcess instance.
        @athena: TBD
        """
        result = self.runner.run(
            [sys.executable, "-c", "print('test')"]
        )

        self.assertIsInstance(result, subprocess.CompletedProcess)
        self.assertEqual(result.returncode, 0)

    def test_run_suppresses_both_stdout_and_stderr(self):
        """
        run() suppresses both stdout and stderr simultaneously.
        @athena: TBD
        """
        # Command that writes to both stdout and stderr
        result = self.runner.run(
            [sys.executable, "-c",
             "import sys; print('stdout'); sys.stderr.write('stderr\\n')"]
        )

        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stdout)
        self.assertIsNone(result.stderr)


class TestMakeProcessRunner(unittest.TestCase):
    """
    Tests for make_process_runner factory function.
    @athena: 80c9607632a3
    """

    def test_make_process_runner_with_all_returns_passthrough(self):
        """
        make_process_runner(TaskOutputTypes.ALL) returns PassthroughProcessRunner.
        @athena: TBD
        """
        runner = make_process_runner(TaskOutputTypes.ALL)
        self.assertIsInstance(runner, PassthroughProcessRunner)

    def test_make_process_runner_with_none_returns_silent(self):
        """
        make_process_runner(TaskOutputTypes.NONE) returns SilentProcessRunner.
        @athena: TBD
        """
        runner = make_process_runner(TaskOutputTypes.NONE)
        self.assertIsInstance(runner, SilentProcessRunner)

    def test_make_process_runner_with_invalid_raises_error(self):
        """
        make_process_runner() raises ValueError for invalid TaskOutputTypes.
        @athena: TBD
        """
        # Create an invalid enum value by casting
        invalid_value = "invalid"
        with self.assertRaises(ValueError) as cm:
            # We can't create an invalid enum value directly, so we'll test
            # by creating a string that would fail enum validation
            make_process_runner(invalid_value)  # type: ignore

        self.assertIn("Invalid TaskOutputTypes", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
