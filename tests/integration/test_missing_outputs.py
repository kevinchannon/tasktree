"""Integration tests for missing output detection."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tasktree.executor import Executor
from tasktree.parser import Recipe, Task
from tasktree.state import StateManager


class TestMissingOutputsIntegration(unittest.TestCase):
    def test_missing_outputs_integration(self):
        """Integration test for missing outputs scenario.

        1. Run task with outputs successfully
        2. Delete one output file
        3. Run again - should execute and warn
        4. Run third time - should skip (outputs now exist)
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a task that produces an output file
            task = Task(
                name="build",
                cmd=f"echo 'test output' > {project_root / 'output.txt'}",
                outputs=["output.txt"],
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            state_manager = StateManager(project_root)
            state_manager.load()
            executor = Executor(recipe, state_manager)

            # First run - task should execute (never run before)
            statuses = executor.execute_task("build")
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "never_run")
            self.assertTrue((project_root / "output.txt").exists())

            # Second run - task should skip (fresh)
            statuses = executor.execute_task("build")
            self.assertFalse(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "fresh")

            # Delete the output file
            (project_root / "output.txt").unlink()
            self.assertFalse((project_root / "output.txt").exists())

            # Third run - task should execute due to missing outputs
            statuses = executor.execute_task("build")
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "outputs_missing")
            self.assertTrue((project_root / "output.txt").exists())

            # Fourth run - task should skip again (outputs exist)
            statuses = executor.execute_task("build")
            self.assertFalse(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "fresh")

    def test_partial_outputs_missing_triggers_rerun(self):
        """Test that missing some (but not all) outputs triggers rebuild.

        When a task declares multiple outputs but only some exist,
        the task should run to regenerate all outputs.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a task that produces two output files
            task = Task(
                name="build",
                cmd=f"echo 'output1' > {project_root / 'output1.txt'} && echo 'output2' > {project_root / 'output2.txt'}",
                outputs=["output1.txt", "output2.txt"],
            )

            tasks = {"build": task}
            recipe = Recipe(tasks=tasks, project_root=project_root, recipe_path=project_root / "tasktree.yaml")
            state_manager = StateManager(project_root)
            state_manager.load()
            executor = Executor(recipe, state_manager)

            # First run - task should execute and create both outputs
            statuses = executor.execute_task("build")
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "never_run")
            self.assertTrue((project_root / "output1.txt").exists())
            self.assertTrue((project_root / "output2.txt").exists())

            # Second run - task should skip (both outputs exist)
            statuses = executor.execute_task("build")
            self.assertFalse(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "fresh")

            # Delete only one output file
            (project_root / "output1.txt").unlink()
            self.assertFalse((project_root / "output1.txt").exists())
            self.assertTrue((project_root / "output2.txt").exists())

            # Third run - task should execute due to partial missing outputs
            statuses = executor.execute_task("build")
            self.assertTrue(statuses["build"].will_run)
            self.assertEqual(statuses["build"].reason, "outputs_missing")
            self.assertIn("output1.txt", statuses["build"].changed_files)

            # Both outputs should exist again
            self.assertTrue((project_root / "output1.txt").exists())
            self.assertTrue((project_root / "output2.txt").exists())


if __name__ == "__main__":
    unittest.main()
