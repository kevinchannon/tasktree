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


@unittest.skipUnless(is_docker_available(), "Docker not available")
class TestDockerDependencyTrackingDirectoryOutputs(unittest.TestCase):
    """
    Test that Docker-runner tasks correctly track dependency outputs when the
    output of a dependency is a directory of files.

    This simulates a build step that produces executables into a directory,
    followed by a test step that should only re-run when executables change.
    """

    def test_docker_runner_task_reruns_when_file_deleted_from_dependency_output_dir(self):
        """
        Verify 'bar' re-runs when a file is deleted from 'foo's output directory.

        'foo' has no explicit inputs. Its command is idempotent: files are only
        written if they do not already exist in build/bin. This means when 'foo'
        runs but its outputs are unchanged, 'bar' should be skipped.

        When a file is deleted from 'foo's output directory and 'foo' recreates it
        (with a new mtime), 'bar' should detect the implicit input change and re-run.

        Test sequence:
        1. First run — 'foo' creates build/bin/exe1 and build/bin/exe2; 'bar' runs.
        2. Second run — outputs unchanged (idempotent cmd); 'bar' skips.
        3. Delete build/bin/exe1 — 'foo' should detect missing output and recreate it;
           'bar' must re-run because build/bin/exe1 is new.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            docker_dir = project_root / "docker"
            docker_dir.mkdir()
            (docker_dir / "Dockerfile").write_text("FROM alpine:latest\n")

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
    outputs: ["build/bin/*"]
    cmd: >-
      mkdir -p build/bin &&
      ([ -f build/bin/exe1 ] || echo "exe1" > build/bin/exe1) &&
      ([ -f build/bin/exe2 ] || echo "exe2" > build/bin/exe2)

  bar:
    run_in: docker
    deps: [foo]
    outputs: [bar-output.txt]
    cmd: ls build/bin | sort > bar-output.txt
"""
            (project_root / "tasktree.yaml").write_text(recipe)

            # First run: both tasks must execute.
            result = run_tasktree_cli(["bar"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"First run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            exe1 = project_root / "build" / "bin" / "exe1"
            exe2 = project_root / "build" / "bin" / "exe2"
            bar_out = project_root / "bar-output.txt"
            self.assertTrue(exe1.exists(), "exe1 was not created on first run")
            self.assertTrue(exe2.exists(), "exe2 was not created on first run")
            self.assertTrue(bar_out.exists(), "bar-output.txt was not created on first run")
            bar_mtime_1 = bar_out.stat().st_mtime
            exe1_mtime_1 = exe1.stat().st_mtime
            exe2_mtime_1 = exe2.stat().st_mtime

            # Second run: foo runs (idempotent — outputs unchanged); bar skips.
            result = run_tasktree_cli(["bar"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"Second run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            bar_mtime_2 = bar_out.stat().st_mtime
            self.assertEqual(
                bar_mtime_1,
                bar_mtime_2,
                "bar-output.txt was unexpectedly updated on second run (bar should have been skipped)",
            )
            self.assertEqual(
                exe1.stat().st_mtime,
                exe1_mtime_1,
                "exe1 should not have been modified on second run (foo's command is idempotent)",
            )
            self.assertEqual(
                exe2.stat().st_mtime,
                exe2_mtime_1,
                "exe2 should not have been modified on second run (foo's command is idempotent)",
            )

            # Delete one of foo's output files.
            exe1.unlink()

            # Third run: foo must detect the missing output and recreate exe1;
            # bar must then re-run because its implicit input (exe1) has changed.
            result = run_tasktree_cli(["bar"], cwd=project_root, timeout=120)
            self.assertEqual(
                result.returncode,
                0,
                f"Third run failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            self.assertTrue(exe1.exists(), "foo should have recreated exe1 after it was deleted")
            bar_content_3 = bar_out.read_text()
            self.assertIn(
                "exe1",
                bar_content_3,
                "'bar' should have re-run and its output should list exe1 (recreated by foo)",
            )
            bar_mtime_3 = bar_out.stat().st_mtime
            self.assertGreater(
                bar_mtime_3,
                bar_mtime_2,
                "'bar' should have re-run (bar-output.txt mtime should have increased)",
            )


if __name__ == "__main__":
    unittest.main()
