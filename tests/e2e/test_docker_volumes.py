"""E2E tests for Docker volume mounts."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerVolumes(unittest.TestCase):
    """Test Docker volume mount functionality."""

    @classmethod
    def setUpClass(cls):
        """Ensure Docker is available before running tests."""
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_relative_volume_mount(self):
        """Test that relative volume paths resolve correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create src directory
            (project_root / "src").mkdir()

            # Create recipe with relative volume mount
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./src:/workspace/src"]

tasks:
  write:
    env: alpine
    outputs: [src/from_container.txt]
    cmd: echo "created in container" > /workspace/src/from_container.txt
""")

            # Execute
            result = run_tasktree_cli(["write"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify file accessible on host via relative path
            output_file = project_root / "src" / "from_container.txt"
            self.assertTrue(output_file.exists(), "File not accessible on host")
            self.assertEqual(
                output_file.read_text().strip(),
                "created in container"
            )

    def test_absolute_volume_mount(self):
        """Test that absolute volume paths work correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            absolute_data_dir = project_root / "data"
            absolute_data_dir.mkdir()

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create recipe with absolute volume mount
            (project_root / "tasktree.yaml").write_text(f"""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["{absolute_data_dir}:/app/data"]

tasks:
  absolute:
    env: alpine
    outputs: [data/absolute.txt]
    cmd: echo "absolute path mount" > /app/data/absolute.txt
""")

            # Execute
            result = run_tasktree_cli(["absolute"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify file accessible via absolute path
            output_file = absolute_data_dir / "absolute.txt"
            self.assertTrue(output_file.exists(), "File not accessible via absolute path")
            self.assertEqual(
                output_file.read_text().strip(),
                "absolute path mount"
            )

    def test_multiple_volume_mounts(self):
        """Test that multiple volumes can be mounted simultaneously."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create multiple directories
            (project_root / "input").mkdir()
            (project_root / "output").mkdir()

            # Create input file
            (project_root / "input" / "source.txt").write_text("input data")

            # Create recipe with multiple volume mounts
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes:
      - "./input:/workspace/input"
      - "./output:/workspace/output"

tasks:
  process:
    env: alpine
    outputs: [output/processed.txt]
    cmd: |
      cat /workspace/input/source.txt > /workspace/output/processed.txt
      echo " - processed" >> /workspace/output/processed.txt
""")

            # Execute
            result = run_tasktree_cli(["process"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify both mounts worked
            input_file = project_root / "input" / "source.txt"
            output_file = project_root / "output" / "processed.txt"

            self.assertTrue(input_file.exists(), "Input mount not accessible")
            self.assertTrue(output_file.exists(), "Output mount not accessible")

            # Verify processing occurred
            content = output_file.read_text()
            self.assertIn("input data", content)
            self.assertIn("processed", content)

    def test_read_and_write_to_volume(self):
        """Test bidirectional access to volume (read and write)."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create data directory with existing file
            (project_root / "data").mkdir()
            (project_root / "data" / "config.txt").write_text("mode=debug")

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./data:/workspace/data"]

tasks:
  readwrite:
    env: alpine
    outputs: [data/result.txt]
    cmd: |
      # Read existing file
      MODE=$(cat /workspace/data/config.txt)
      # Write new file based on read
      echo "Config: $MODE" > /workspace/data/result.txt
""")

            # Execute
            result = run_tasktree_cli(["readwrite"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify read and write both worked
            result_file = project_root / "data" / "result.txt"
            self.assertTrue(result_file.exists(), "Write to volume failed")
            self.assertIn("mode=debug", result_file.read_text())


if __name__ == "__main__":
    unittest.main()
