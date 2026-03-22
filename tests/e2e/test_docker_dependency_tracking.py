"""E2E tests for Docker runner dependency output tracking.

Verifies that a task running in a Docker container re-runs when the output
of one of its dependencies changes — even when both tasks use a Docker runner
with the Dockerfile in a project subdirectory.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


@unittest.skipUnless(is_docker_available(), "Docker not available")
class TestDockerDependencyTracking(unittest.TestCase):
    """
    Test that Docker-runner tasks correctly re-run when dependency outputs change.

    This covers the bug where Docker-runner tasks appeared to only re-run when the
    Dockerfile changed, rather than when the output of a dependency task changed.
    """

    def test_docker_runner_task_reruns_when_dependency_output_changes(self):
        """
        Verify that 'bar' re-runs when 'foo's output changes, both using a Docker runner.

        The runner uses a Dockerfile in a subdirectory (docker/Dockerfile) and sets
        the container working directory to the project root via {{ tt.project_root }}.
        The project root is mounted into the container at the same path so that
        relative output/input paths resolve correctly on both host and in container.

        'foo' has an input file (source.txt) so it can be skipped when nothing
        changes.  We then modify foo-output.txt directly (without touching
        source.txt) to simulate the dependency output changing independently,
        and verify that 'bar' re-runs.

        Test sequence:
        1. First run — both 'foo' and 'bar' execute (no prior state).
        2. Second run — both skip (source.txt unchanged, outputs still fresh).
        3. Modify 'foo-output.txt' directly, bypassing 'foo's tracking.
        4. Third run — 'bar' must re-run because its implicit input changed.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Place the Dockerfile in a subdirectory, as required by the issue.
            docker_dir = project_root / "docker"
            docker_dir.mkdir()
            (docker_dir / "Dockerfile").write_text(
                "FROM alpine:latest\n"
            )

            # 'foo' must have an input so it can be skipped on subsequent runs.
            # Tasks with no inputs always re-run, which would defeat this test.
            (project_root / "source.txt").write_text("initial\n")

            # The runner mounts the project root into the container at the same
            # absolute path so that {{ tt.project_root }} is a valid working dir.
            recipe = """\
runners:
  docker:
    dockerfile: docker/Dockerfile
    context: docker
    volumes:
      - "{{ tt.project_root }}:{{ tt.project_root }}"
    working_dir: "{{ tt.project_root }}"

tasks:
  foo:
    run_in: docker
    inputs: [source.txt]
    outputs: [foo-output.txt]
    cmd: cat source.txt > foo-output.txt

  bar:
    run_in: docker
    deps: [foo]
    outputs: [bar-output.txt]
    cmd: cat foo-output.txt > bar-output.txt
"""
            (project_root / "tasktree.yaml").write_text(recipe)

            # First run: both tasks must execute.
            result = run_tasktree_cli(["bar"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"First run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertTrue(
                (project_root / "foo-output.txt").exists(),
                "foo-output.txt was not created on first run",
            )
            self.assertTrue(
                (project_root / "bar-output.txt").exists(),
                "bar-output.txt was not created on first run",
            )
            foo_mtime_1 = (project_root / "foo-output.txt").stat().st_mtime
            bar_mtime_1 = (project_root / "bar-output.txt").stat().st_mtime

            # Second run: both tasks should be skipped (outputs are fresh).
            result = run_tasktree_cli(["bar"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"Second run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            foo_mtime_2 = (project_root / "foo-output.txt").stat().st_mtime
            bar_mtime_2 = (project_root / "bar-output.txt").stat().st_mtime
            self.assertEqual(
                foo_mtime_1,
                foo_mtime_2,
                "foo-output.txt was unexpectedly updated on second run (task should have been skipped)",
            )
            self.assertEqual(
                bar_mtime_1,
                bar_mtime_2,
                "bar-output.txt was unexpectedly updated on second run (task should have been skipped)",
            )

            # Modify foo-output.txt directly, bypassing 'foo's input tracking so
            # that only 'bar's implicit-input tracking is exercised.
            (project_root / "foo-output.txt").write_text("modified foo content\n")

            # Third run: 'bar' must re-run because its implicit input changed.
            result = run_tasktree_cli(["bar"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"Third run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            bar_content_3 = (project_root / "bar-output.txt").read_text()
            self.assertIn(
                "modified foo content",
                bar_content_3,
                "'bar' should have re-run and copied the modified foo-output.txt content into bar-output.txt",
            )


if __name__ == "__main__":
    unittest.main()
