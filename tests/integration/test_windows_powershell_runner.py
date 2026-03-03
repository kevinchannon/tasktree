"""Integration tests for PowerShell runner on Windows."""

import sys
import tempfile
import unittest
from pathlib import Path

from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager

from helpers.logging import logger_stub
from fixture_utils import copy_fixture_files


@unittest.skipUnless(sys.platform == "win32", "Windows-only test")
class TestWindowsPowershellRunner(unittest.TestCase):
    """
    Test that a task configured with a PowerShell runner executes in PowerShell.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.recipe_file = Path(self.test_dir) / "tasktree.yaml"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_powershell_runner_executes_in_powershell(self):
        """
        Test that a task with a PowerShell runner runs commands in PowerShell.

        Uses Write-Output which is a PowerShell-specific cmdlet that would fail
        in cmd.exe, verifying the task is actually executing in PowerShell.
        """
        copy_fixture_files("powershell_runner", Path(self.test_dir))

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state, logger_stub, make_process_runner)
        executor.execute_task("one", TaskOutputTypes.ALL)

        output_file = Path(self.test_dir) / "output.txt"
        self.assertTrue(output_file.exists(), "Output file was not created by PowerShell runner")
        content = output_file.read_text(encoding="utf-8").strip()
        self.assertIn("from-powershell", content)


if __name__ == "__main__":
    unittest.main()
