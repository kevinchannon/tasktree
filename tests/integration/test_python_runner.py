"""Integration tests for Python shell runner."""

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app
from fixture_utils import copy_fixture_files


@unittest.skipUnless(sys.platform != "win32", "POSIX-only: Python runner uses shebang-based script execution")
class TestPythonRunner(unittest.TestCase):
    """
    Test that a task configured with a Python runner executes Python code.

    Commands are written to a temporary script file with a #!/usr/bin/env python3
    shebang and executed directly, so cmd: [python3] (without -c) is the correct
    and sufficient configuration.
    """

    def setUp(self):
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_python_runner_executes_python_code(self):
        """
        Test that a task with cmd: [python3] runner executes Python code correctly.

        The task cmd is written to a script file with a #!/usr/bin/env python3 shebang
        and executed directly — no -c flag is needed or used.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            original_cwd = os.getcwd()

            try:
                os.chdir(project_root)
                copy_fixture_files("python_runner", project_root)

                result = self.runner.invoke(app, ["run-python"], env=self.env)

                self.assertEqual(
                    result.exit_code,
                    0,
                    f"Command failed: {result.stdout}",
                )

                output_file = project_root / "output.txt"
                self.assertTrue(output_file.exists(), "Output file was not created by Python runner")
                content = output_file.read_text().strip()
                self.assertIn("from-python-3", content)
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
