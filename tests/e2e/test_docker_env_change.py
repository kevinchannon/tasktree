"""E2E tests for environment-change detection via the image content fingerprint.

A containerised task must re-run when its build environment changes (e.g. a
Dockerfile edit), even if its declared inputs/outputs are unchanged. Tasktree no
longer tracks Docker build inputs host-side; instead it compares the built
image's content fingerprint (RootFS layers) after the freshness probe builds the
image. These tests exercise that end-to-end against real Docker.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerEnvironmentChange(unittest.TestCase):
    """
    Test that container image content changes re-run tasks; identical ones skip.
    """

    @classmethod
    def setUpClass(cls):
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def _write_project(self, project_root: Path, dockerfile: str) -> None:
        (project_root / "Dockerfile").write_text(dockerfile)
        # An input lets the task be skipped when nothing relevant changed (tasks
        # with no inputs always run).
        (project_root / "source.txt").write_text("data\n")
        (project_root / "tasktree.yaml").write_text("""
runners:
  alpine:
    type: containerised
    engine: docker
    dockerfile: ./Dockerfile
    context: .

tasks:
  build:
    run_in: alpine
    inputs: [source.txt]
    outputs: [out.txt]
    cmd: cat source.txt > out.txt
""")

    def test_dockerfile_change_reruns_task_unchanged_skips(self):
        """
        First run executes; an unchanged environment + inputs skips; a Dockerfile
        edit (which changes the image content) re-runs even though inputs are
        unchanged.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            self._write_project(project_root, "FROM alpine:latest\n")
            out = project_root / "out.txt"

            # First run — executes (no prior state).
            result = run_tasktree_cli(["build"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"First run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertTrue(out.exists(), "out.txt not created on first run")
            mtime_1 = out.stat().st_mtime

            # Second run — nothing changed: image rebuild is a cache hit with an
            # identical content fingerprint, inputs unchanged, output present → skip.
            result = run_tasktree_cli(["build"], cwd=project_root, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                out.stat().st_mtime,
                mtime_1,
                "Task unexpectedly re-ran when nothing changed",
            )

            # Change the Dockerfile so the built image content differs.
            self._write_project(
                project_root, "FROM alpine:latest\nRUN touch /env-marker\n"
            )

            # Third run — must re-run because the image fingerprint changed, even
            # though source.txt is unchanged.
            result = run_tasktree_cli(["build"], cwd=project_root, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(
                out.stat().st_mtime,
                mtime_1,
                "Task did not re-run after the Dockerfile (environment) changed",
            )


if __name__ == "__main__":
    unittest.main()
