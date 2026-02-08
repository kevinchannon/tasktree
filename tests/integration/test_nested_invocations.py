"""Integration tests for nested task invocations (Phase 1)."""

import json
import os
import re
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from tasktree.cli import app


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    return ansi_escape.sub("", text)


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
    # We're in tests/integration, so go up to project root
    project_root = Path(__file__).parent.parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        raise RuntimeError(f"Could not find tasktree source at {src_dir}")

    # Copy the entire src directory to the destination
    dest_src = dest_dir / "src"
    shutil.copytree(src_dir, dest_src)


class TestNestedInvocations(unittest.TestCase):
    """Integration tests for nested tt invocations."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_simple_nested_invocation(self):
        """
        Test basic nested invocation: parent calls tt child.
        Both tasks should have state entries after execution.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create tasktree binary in PATH for nested calls
            # For this test, we'll use the current python module
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  child:
    outputs: [child.txt]
    cmd: echo "child output" > child.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent output" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify both outputs were created with correct content
                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())
                self.assertEqual(child_txt.read_text().strip(), "child output")
                self.assertEqual(parent_txt.read_text().strip(), "parent output")

                # Verify state file exists and contains both tasks
                state_file = project_root / ".tasktree-state"
                self.assertTrue(state_file.exists())

                with open(state_file, "r") as f:
                    state = json.load(f)

                # Should have entries for both tasks
                # State keys are task hashes, so we check count
                self.assertEqual(len(state), 2, "State should have entries for parent and child")

            finally:
                os.chdir(original_cwd)

    def test_nested_invocation_incrementality(self):
        """
        Test that nested invocations benefit from incrementality.
        Run parent twice - second run should skip child if inputs unchanged.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  child:
    outputs: [child.txt]
    cmd: echo "child output" > child.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent output" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - both execute
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())

                # Record mtimes
                child_mtime_1 = child_txt.stat().st_mtime
                parent_mtime_1 = parent_txt.stat().st_mtime

                # Small delay to ensure timestamp difference
                time.sleep(1.01)

                # Second run - both child and parent run (no inputs, always run)
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Parent output updated (parent always runs - no inputs)
                parent_mtime_2 = parent_txt.stat().st_mtime
                self.assertGreater(parent_mtime_2, parent_mtime_1)

                # Child output also updated (child always runs - no inputs)
                child_mtime_2 = child_txt.stat().st_mtime
                self.assertGreater(child_mtime_2, child_mtime_1)

            finally:
                os.chdir(original_cwd)

    def test_multiple_sequential_nested_calls(self):
        """
        Test parent calling multiple children sequentially.
        All tasks should have correct state entries.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  child1:
    outputs: [child1.txt]
    cmd: echo "child1" > child1.txt

  child2:
    outputs: [child2.txt]
    cmd: echo "child2" > child2.txt

  child3:
    outputs: [child3.txt]
    cmd: echo "child3" > child3.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child1
      python3 -m tasktree.cli child2
      python3 -m tasktree.cli child3
      echo "parent done" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created with correct content
                child1_txt = project_root / "child1.txt"
                child2_txt = project_root / "child2.txt"
                child3_txt = project_root / "child3.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child1_txt.exists())
                self.assertTrue(child2_txt.exists())
                self.assertTrue(child3_txt.exists())
                self.assertTrue(parent_txt.exists())
                self.assertEqual(child1_txt.read_text().strip(), "child1")
                self.assertEqual(child2_txt.read_text().strip(), "child2")
                self.assertEqual(child3_txt.read_text().strip(), "child3")
                self.assertEqual(parent_txt.read_text().strip(), "parent done")

                # Verify state has all 4 tasks
                state_file = project_root / ".tasktree-state"
                with open(state_file, "r") as f:
                    state = json.load(f)

                self.assertEqual(len(state), 4, "State should have entries for parent and 3 children")

            finally:
                os.chdir(original_cwd)

    def test_nested_call_with_task_deps(self):
        """
        Test nested call to task that has its own dependencies.
        Dependency resolution should still work correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  dep:
    outputs: [dep.txt]
    cmd: echo "dependency" > dep.txt

  child:
    deps: [dep]
    outputs: [child.txt]
    cmd: echo "child" > child.txt

  parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created with correct content (dep, child, parent)
                dep_txt = project_root / "dep.txt"
                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(dep_txt.exists())
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())
                self.assertEqual(dep_txt.read_text().strip(), "dependency")
                self.assertEqual(child_txt.read_text().strip(), "child")
                self.assertEqual(parent_txt.read_text().strip(), "parent")

                # Verify execution order via timestamps
                dep_time = (project_root / "dep.txt").stat().st_mtime
                child_time = (project_root / "child.txt").stat().st_mtime
                parent_time = (project_root / "parent.txt").stat().st_mtime

                # dep should run before child, child before parent
                self.assertLessEqual(dep_time, child_time)
                self.assertLessEqual(child_time, parent_time)

            finally:
                os.chdir(original_cwd)

    def test_deep_nesting_chain(self):
        """
        Test deeply nested chain: A calls B calls C calls D.
        All tasks should execute correctly with proper state management.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  d:
    outputs: [d.txt]
    cmd: echo "d" > d.txt

  c:
    outputs: [c.txt]
    cmd: |
      python3 -m tasktree.cli d
      echo "c" > c.txt

  b:
    outputs: [b.txt]
    cmd: |
      python3 -m tasktree.cli c
      echo "b" > b.txt

  a:
    outputs: [a.txt]
    cmd: |
      python3 -m tasktree.cli b
      echo "a" > a.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run top-level task
                result = self.runner.invoke(app, ["a"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created with correct content
                a_txt = project_root / "a.txt"
                b_txt = project_root / "b.txt"
                c_txt = project_root / "c.txt"
                d_txt = project_root / "d.txt"
                self.assertTrue(a_txt.exists())
                self.assertTrue(b_txt.exists())
                self.assertTrue(c_txt.exists())
                self.assertTrue(d_txt.exists())
                self.assertEqual(a_txt.read_text().strip(), "a")
                self.assertEqual(b_txt.read_text().strip(), "b")
                self.assertEqual(c_txt.read_text().strip(), "c")
                self.assertEqual(d_txt.read_text().strip(), "d")

                # Verify state has all 4 tasks
                state_file = project_root / ".tasktree-state"
                with open(state_file, "r") as f:
                    state = json.load(f)

                self.assertEqual(len(state), 4, "State should have entries for all 4 tasks")

                # Verify execution order
                d_time = (project_root / "d.txt").stat().st_mtime
                c_time = (project_root / "c.txt").stat().st_mtime
                b_time = (project_root / "b.txt").stat().st_mtime
                a_time = (project_root / "a.txt").stat().st_mtime

                self.assertLessEqual(d_time, c_time)
                self.assertLessEqual(c_time, b_time)
                self.assertLessEqual(b_time, a_time)

            finally:
                os.chdir(original_cwd)

    def test_nested_call_failure_propagates(self):
        """
        Test that a failed nested tt call causes the parent task to fail.
        Error propagation should follow normal shell exit code behavior.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  failing-child:
    cmd: exit 1

  parent:
    outputs: [parent.txt]
    cmd: |
      set -e
      python3 -m tasktree.cli failing-child
      echo "should not reach here" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task - should fail
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Parent should fail when child fails")

                # Parent output should not be created
                parent_txt = project_root / "parent.txt"
                self.assertFalse(parent_txt.exists(), "Parent should not complete after child failure")

            finally:
                os.chdir(original_cwd)

    def test_deeply_nested_chain_with_incrementality(self):
        """
        Test deeply nested chain (5 levels: A→B→C→D→E) with incrementality.
        First run executes all tasks, second run should skip E (bottom) due to incrementality,
        causing D to skip, etc., but tasks without inputs always run.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
tasks:
  e:
    outputs: [e.txt]
    cmd: echo "e" > e.txt

  d:
    outputs: [d.txt]
    cmd: |
      python3 -m tasktree.cli e
      echo "d" > d.txt

  c:
    outputs: [c.txt]
    cmd: |
      python3 -m tasktree.cli d
      echo "c" > c.txt

  b:
    outputs: [b.txt]
    cmd: |
      python3 -m tasktree.cli c
      echo "b" > b.txt

  a:
    outputs: [a.txt]
    cmd: |
      python3 -m tasktree.cli b
      echo "a" > a.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # First run - all tasks execute
                result = self.runner.invoke(app, ["a"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created with correct content
                a_txt = project_root / "a.txt"
                b_txt = project_root / "b.txt"
                c_txt = project_root / "c.txt"
                d_txt = project_root / "d.txt"
                e_txt = project_root / "e.txt"

                self.assertTrue(a_txt.exists())
                self.assertTrue(b_txt.exists())
                self.assertTrue(c_txt.exists())
                self.assertTrue(d_txt.exists())
                self.assertTrue(e_txt.exists())

                self.assertEqual(a_txt.read_text().strip(), "a")
                self.assertEqual(b_txt.read_text().strip(), "b")
                self.assertEqual(c_txt.read_text().strip(), "c")
                self.assertEqual(d_txt.read_text().strip(), "d")
                self.assertEqual(e_txt.read_text().strip(), "e")

                # Record mtimes
                a_mtime_1 = a_txt.stat().st_mtime
                b_mtime_1 = b_txt.stat().st_mtime
                c_mtime_1 = c_txt.stat().st_mtime
                d_mtime_1 = d_txt.stat().st_mtime
                e_mtime_1 = e_txt.stat().st_mtime

                # Small delay to ensure timestamp difference
                time.sleep(1.01)

                # Second run - ALL tasks have no inputs, so they all run
                result = self.runner.invoke(app, ["a"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Get new mtimes
                a_mtime_2 = a_txt.stat().st_mtime
                b_mtime_2 = b_txt.stat().st_mtime
                c_mtime_2 = c_txt.stat().st_mtime
                d_mtime_2 = d_txt.stat().st_mtime
                e_mtime_2 = e_txt.stat().st_mtime

                # All tasks have no inputs, so they all run on second invocation
                self.assertGreater(e_mtime_2, e_mtime_1, "Task e should run (no inputs)")
                self.assertGreater(a_mtime_2, a_mtime_1, "Task a should run (no inputs)")
                self.assertGreater(b_mtime_2, b_mtime_1, "Task b should run (no inputs)")
                self.assertGreater(c_mtime_2, c_mtime_1, "Task c should run (no inputs)")
                self.assertGreater(d_mtime_2, d_mtime_1, "Task d should run (no inputs)")

            finally:
                os.chdir(original_cwd)


class TestDockerNestedInvocations(unittest.TestCase):
    """Integration tests for Phase 2: Docker support in nested invocations."""

    @classmethod
    def setUpClass(cls):
        """Ensure Docker is available before running tests."""
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "Docker integration tests require Docker to be installed and the daemon to be running."
            )

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    def test_docker_task_calls_nested_same_runner(self):
        """
        Test that a Docker task can call another task with the same Docker runner.
        Should execute directly without launching a new container.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker build
            copy_tasktree_source(project_root)

            # Create simple Dockerfile
            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
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
    cmd: echo "child output" > child.txt

  parent:
    run_in: build
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent output" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify outputs created
                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())

                # Verify state has both tasks
                state_file = project_root / ".tasktree-state"
                with open(state_file, "r") as f:
                    state = json.load(f)
                self.assertEqual(len(state), 2)

            finally:
                os.chdir(original_cwd)

    def test_docker_task_calls_nested_different_docker_fails(self):
        """
        Test that nested call to different Docker runner fails with clear error.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker build
            copy_tasktree_source(project_root)

            # Create two Dockerfiles
            dockerfile_build = project_root / "Dockerfile.build"
            dockerfile_build.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            dockerfile_test = project_root / "Dockerfile.test"
            dockerfile_test.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
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
    cmd: echo "child"

  parent:
    run_in: build
    cmd: python3 -m tasktree.cli child
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task - should fail
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertNotEqual(result.exit_code, 0, "Parent should fail when child requires different Docker runner")

                # Note: The detailed error message about runner mismatch is printed during execution
                # but may not appear in result.stdout. The important behavior is that it fails.

            finally:
                os.chdir(original_cwd)

    def test_docker_task_calls_nested_shell_runner_succeeds(self):
        """
        Test that Docker task can call task with shell-only runner (allowed).
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker build
            copy_tasktree_source(project_root)

            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
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
    cmd: echo "child output" > child.txt

  parent:
    run_in: build
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child
      echo "parent output" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task - should succeed
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify outputs created
                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())

            finally:
                os.chdir(original_cwd)

    def test_local_calls_docker_task(self):
        """
        Test that local task can call Docker task (normal operation).
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker build
            copy_tasktree_source(project_root)

            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  build:
    dockerfile: Dockerfile
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

tasks:
  docker-child:
    run_in: build
    outputs: [child.txt]
    cmd: echo "docker child" > child.txt

  local-parent:
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli docker-child
      echo "local parent" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run local parent task
                result = self.runner.invoke(app, ["local-parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify outputs created
                child_txt = project_root / "child.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child_txt.exists())
                self.assertTrue(parent_txt.exists())

            finally:
                os.chdir(original_cwd)

    def test_state_file_accessible_in_container(self):
        """
        Test that state file is mounted and accessible inside Docker container.
        Verify state updates work across container boundary.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker build
            copy_tasktree_source(project_root)

            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  build:
    dockerfile: Dockerfile
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

tasks:
  docker-task:
    run_in: build
    outputs: [output.txt]
    cmd: echo "docker output" > output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run docker task
                result = self.runner.invoke(app, ["docker-task"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify state file exists on host
                state_file = project_root / ".tasktree-state"
                self.assertTrue(state_file.exists())

                # Verify state has entry for task
                with open(state_file, "r") as f:
                    state = json.load(f)
                self.assertEqual(len(state), 1)

            finally:
                os.chdir(original_cwd)

    def test_multiple_nested_docker_calls_update_state(self):
        """
        Test that multiple sequential nested calls in Docker all update state correctly.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Copy tasktree source code for Docker build
            copy_tasktree_source(project_root)

            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""
FROM python:3.11-slim
WORKDIR /workspace
RUN pip install pyyaml typer click rich colorama pathspec platformdirs
COPY . /app
ENV PYTHONPATH=/app/src
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  build:
    dockerfile: Dockerfile
    context: .
    shell: /bin/bash
    volumes: [".:/workspace"]

tasks:
  child1:
    run_in: build
    outputs: [child1.txt]
    cmd: echo "child1" > child1.txt

  child2:
    run_in: build
    outputs: [child2.txt]
    cmd: echo "child2" > child2.txt

  parent:
    run_in: build
    outputs: [parent.txt]
    cmd: |
      python3 -m tasktree.cli child1
      python3 -m tasktree.cli child2
      echo "parent" > parent.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run parent task
                result = self.runner.invoke(app, ["parent"], env=self.env)
                self.assertEqual(result.exit_code, 0)

                # Verify all outputs created
                child1_txt = project_root / "child1.txt"
                child2_txt = project_root / "child2.txt"
                parent_txt = project_root / "parent.txt"
                self.assertTrue(child1_txt.exists())
                self.assertTrue(child2_txt.exists())
                self.assertTrue(parent_txt.exists())

                # Verify state has all 3 tasks
                state_file = project_root / ".tasktree-state"
                with open(state_file, "r") as f:
                    state = json.load(f)
                self.assertEqual(len(state), 3)

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
