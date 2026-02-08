"""E2E tests for nested task invocations."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import run_tasktree_cli


def is_docker_available() -> bool:
    """Check if Docker is installed and running.

    Returns:
        True if docker command exists and daemon is running
    """
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return False


def copy_tasktree_source(dest_dir: Path) -> None:
    """Copy tasktree source code to destination directory for Docker builds.

    Args:
        dest_dir: Destination directory (typically a test's temporary directory)
    """
    # Find the tasktree source directory (src/tasktree)
    # We're in tests/e2e, so go up to project root
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        raise RuntimeError(f"Could not find tasktree source at {src_dir}")

    # Copy the entire src directory to the destination
    dest_src = dest_dir / "src"
    shutil.copytree(src_dir, dest_src)


class TestNestedInvocationsE2E(unittest.TestCase):
    """End-to-end tests for nested tt invocations via real subprocess execution."""

    def test_real_subprocess_nested_invocation(self):
        """
        Test nested invocation using real subprocess calls.
        Verifies state file contains both parent and child entries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create recipe with parent→child nesting
            (project_root / "tasktree.yaml").write_text("""
tasks:
  child:
    outputs: [child_output.txt]
    cmd: echo "child executed" > child_output.txt

  parent:
    outputs: [parent_output.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent executed" > parent_output.txt
""")

            # Execute parent task via subprocess
            result = run_tasktree_cli(["parent"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify both output files were created
            child_output = project_root / "child_output.txt"
            parent_output = project_root / "parent_output.txt"

            self.assertTrue(child_output.exists(), "Child output file not created")
            self.assertTrue(parent_output.exists(), "Parent output file not created")

            self.assertEqual(child_output.read_text().strip(), "child executed")
            self.assertEqual(parent_output.read_text().strip(), "parent executed")

            # Verify state file exists and has correct structure
            state_file = project_root / ".tasktree-state"
            self.assertTrue(state_file.exists(), "State file not created")

            with open(state_file, "r") as f:
                state_data = json.load(f)

            # Should have 2 entries (parent and child)
            self.assertEqual(
                len(state_data),
                2,
                f"Expected 2 state entries, got {len(state_data)}",
            )

            # Verify each entry has required fields
            for cache_key, task_state in state_data.items():
                self.assertIn("last_run", task_state)
                self.assertIn("input_state", task_state)
                self.assertIsInstance(task_state["last_run"], (int, float))
                self.assertIsInstance(task_state["input_state"], dict)

    def test_nested_invocation_incrementality_e2e(self):
        """
        Test that incrementality works across nested calls in real execution.
        Second run should skip child if outputs are fresh.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "tasktree.yaml").write_text("""
tasks:
  child:
    outputs: [child.out]
    cmd: echo "child" > child.out

  parent:
    outputs: [parent.out]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent" > parent.out
""")

            # First run - both execute
            result1 = run_tasktree_cli(["parent"], cwd=project_root)
            self.assertEqual(result1.returncode, 0)

            child_out = project_root / "child.out"
            parent_out = project_root / "parent.out"

            self.assertTrue(child_out.exists())
            self.assertTrue(parent_out.exists())

            # Record child mtime
            child_mtime_1 = child_out.stat().st_mtime

            # Second run - child should skip (fresh outputs)
            result2 = run_tasktree_cli(["parent"], cwd=project_root)
            self.assertEqual(result2.returncode, 0)

            # Child output should have been regenerated (child has no inputs, always runs)
            child_mtime_2 = child_out.stat().st_mtime
            self.assertGreater(
                child_mtime_2,
                child_mtime_1,
                "Child should run on second invocation (no inputs)",
            )

            # Verify child ran
            self.assertIn("child", result2.stdout.lower())

    def test_complex_topology_real_execution(self):
        """
        Test complex dependency topology with nested calls.
        Diamond pattern: parent calls B and C, both call D.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "tasktree.yaml").write_text("""
tasks:
  d:
    outputs: [d.txt]
    cmd: echo "d" > d.txt

  b:
    outputs: [b.txt]
    cmd: |
      python3 -m tasktree.cli d
      echo "b" > b.txt

  c:
    outputs: [c.txt]
    cmd: |
      python3 -m tasktree.cli d
      echo "c" > c.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli b
      python3 -m tasktree.cli c
      echo "parent" > parent.txt
""")

            # Execute parent
            result = run_tasktree_cli(["parent"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify all outputs created
            self.assertTrue((project_root / "d.txt").exists())
            self.assertTrue((project_root / "b.txt").exists())
            self.assertTrue((project_root / "c.txt").exists())
            self.assertTrue((project_root / "parent.txt").exists())

            # Verify state file correctness
            state_file = project_root / ".tasktree-state"
            with open(state_file, "r") as f:
                state_data = json.load(f)

            # Should have 4 entries (d, b, c, parent)
            self.assertEqual(len(state_data), 4)

            # Verify execution order via timestamps
            d_time = (project_root / "d.txt").stat().st_mtime
            b_time = (project_root / "b.txt").stat().st_mtime
            c_time = (project_root / "c.txt").stat().st_mtime
            parent_time = (project_root / "parent.txt").stat().st_mtime

            # With "no inputs = always run", d runs multiple times:
            # - Once when b invokes it
            # - Again when c invokes it
            # So d.txt may have timestamp after b.txt or c.txt
            # Just verify all files exist (timing assertions no longer valid)

            # Verify parent runs last
            self.assertLessEqual(b_time, parent_time)
            self.assertLessEqual(c_time, parent_time)


@unittest.skipUnless(is_docker_available(), "Docker not available")
class TestDockerNestedInvocationsE2E(unittest.TestCase):
    """E2E tests for Phase 2: Docker support in nested invocations."""

    def test_real_docker_nested_invocation(self):
        """
        Test real Docker container with nested tt call.
        Verify state file updates work across container boundary.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker builds
            copy_tasktree_source(project_root)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
runners:
  build:
    dockerfile: Dockerfile
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

tasks:
  child:
    run_in: build
    outputs: [child.txt]
    cmd: echo "docker child" > child.txt

  parent:
    run_in: build
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "docker parent" > parent.txt
""")

            # Execute parent task
            result = run_tasktree_cli(["parent"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify outputs created
            child_txt = project_root / "child.txt"
            parent_txt = project_root / "parent.txt"
            self.assertTrue(child_txt.exists())
            self.assertTrue(parent_txt.exists())

            # Verify state has both entries
            state_file = project_root / ".tasktree-state"
            with open(state_file, "r") as f:
                state_data = json.load(f)
            self.assertEqual(len(state_data), 2)

    def test_real_docker_different_runner_error(self):
        """
        Test that attempting to switch to different Docker runner produces clear error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker builds
            copy_tasktree_source(project_root)

            # Create two Dockerfiles
            (project_root / "Dockerfile.build").write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            (project_root / "Dockerfile.test").write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
runners:
  build:
    dockerfile: Dockerfile.build
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

  test:
    dockerfile: Dockerfile.test
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

tasks:
  child:
    run_in: test
    cmd: echo "test child"

  parent:
    run_in: build
    cmd: python3 -m tasktree.cli child
""")

            # Execute parent task - should fail
            result = run_tasktree_cli(["parent"], cwd=project_root)

            self.assertNotEqual(result.returncode, 0, "Should fail when switching Docker runners")

            # Verify error message
            error_output = result.stderr + result.stdout
            self.assertIn("requires containerized runner 'test'", error_output)
            self.assertIn("currently executing inside runner 'build'", error_output)

    def test_real_docker_shell_runner_switch(self):
        """
        Test that switching from Docker runner to shell-only runner works.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker builds
            copy_tasktree_source(project_root)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
runners:
  build:
    dockerfile: Dockerfile
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

  lint:
    shell: /bin/sh
    preamble: "set -e"

tasks:
  child:
    run_in: lint
    outputs: [child.txt]
    cmd: echo "shell child" > child.txt

  parent:
    run_in: build
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "docker parent" > parent.txt
""")

            # Execute parent task - should succeed
            result = run_tasktree_cli(["parent"], cwd=project_root)

            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify outputs created
            child_txt = project_root / "child.txt"
            parent_txt = project_root / "parent.txt"
            self.assertTrue(child_txt.exists())
            self.assertTrue(parent_txt.exists())


if __name__ == "__main__":
    unittest.main()
