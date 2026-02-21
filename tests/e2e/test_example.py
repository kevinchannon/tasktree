"""E2E tests that run tasks from the project's own example/ directory."""

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli

EXAMPLE_DIR = Path(__file__).parent.parent.parent / "example"


def copy_example(dest: Path) -> Path:
    """Copy the example directory tree into dest and return the path."""
    project_root = dest / "example"
    shutil.copytree(EXAMPLE_DIR, project_root)
    return project_root


class TestExampleRecipe(unittest.TestCase):
    """Run tasks from the bundled example recipe to verify real-world workflows."""

    def test_build_task_creates_output(self):
        """build task produces an output file under build/."""
        with TemporaryDirectory() as tmpdir:
            project_root = copy_example(Path(tmpdir))

            result = run_tasktree_cli(["build"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"build failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            output = project_root / "build" / "output-debug-x86_64.txt"
            self.assertTrue(output.exists(), "build output file not created")

    def test_transform_task_converts_source_to_uppercase(self):
        """transform task reads source.txt and writes an upper-cased result."""
        with TemporaryDirectory() as tmpdir:
            project_root = copy_example(Path(tmpdir))

            result = run_tasktree_cli(["transform"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"transform failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            result_file = project_root / "processed" / "result.txt"
            self.assertTrue(result_file.exists(), "transform result file not created")
            self.assertEqual(
                result_file.read_text(),
                (project_root / "source.txt").read_text().upper(),
            )

    def test_imported_show_info_task_runs(self):
        """utils.show-info (imported task) runs successfully."""
        with TemporaryDirectory() as tmpdir:
            project_root = copy_example(Path(tmpdir))

            result = run_tasktree_cli(["utils.show-info"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"utils.show-info failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

    def test_imported_pinned_task_creates_report(self):
        """utils.generate-report (pinned imported task) writes a report file."""
        with TemporaryDirectory() as tmpdir:
            project_root = copy_example(Path(tmpdir))

            result = run_tasktree_cli(["utils.generate-report"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"utils.generate-report failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            report = project_root / "reports" / "build-report.txt"
            self.assertTrue(report.exists(), "report file not created")
            self.assertIn("Build Report", report.read_text())

    def test_clean_resets_state_and_tasks_rerun(self):
        """--clean removes the state file; subsequent tasks run from scratch."""
        with TemporaryDirectory() as tmpdir:
            project_root = copy_example(Path(tmpdir))

            # First run
            result = run_tasktree_cli(["transform"], cwd=project_root)
            self.assertEqual(
                result.returncode,
                0,
                f"First transform failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            state_file = project_root / ".tasktree-state"
            self.assertTrue(state_file.exists(), "state file not created after first run")

            # Clear state
            result = run_tasktree_cli(["--clean"], cwd=project_root)
            self.assertEqual(
                result.returncode,
                0,
                f"--clean failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertFalse(state_file.exists(), "state file still present after --clean")

            # Re-run after clean — task must execute again (not be skipped)
            result = run_tasktree_cli(["transform"], cwd=project_root)
            self.assertEqual(
                result.returncode,
                0,
                f"transform after --clean failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            # "Running:" appears in stdout when a task actually executes (not when skipped)
            self.assertIn(
                "Running: transform",
                result.stdout,
                "transform was skipped after --clean instead of re-running",
            )
            result_file = project_root / "processed" / "result.txt"
            self.assertTrue(result_file.exists(), "transform output not present after re-run")

    @unittest.skipUnless(is_docker_available(), "Docker not available")
    def test_docker_echo_task_creates_output(self):
        """docker-echo task creates an output file via a Docker container."""
        with TemporaryDirectory() as tmpdir:
            project_root = copy_example(Path(tmpdir))

            # Use a generous timeout: cold CI runners may need time to pull/build the image
            result = run_tasktree_cli(["docker-echo"], cwd=project_root, timeout=120)

            self.assertEqual(
                result.returncode,
                0,
                f"docker-echo failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            output = project_root / "output" / "docker-result.txt"
            self.assertTrue(output.exists(), "docker-echo output file not created")
            self.assertIn("Hello from Docker", output.read_text())


if __name__ == "__main__":
    unittest.main()
