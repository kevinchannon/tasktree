"""E2E tests for basic Docker execution."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerBasic(unittest.TestCase):
    """Test basic Docker container execution."""

    @classmethod
    def setUpClass(cls):
        """Ensure Docker is available before running tests."""
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_simple_echo_in_container(self):
        """Test that basic command executes in Docker container."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create data directory
            (project_root / "data").mkdir()

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./data:/workspace/data"]

tasks:
  hello:
    env: alpine
    outputs: [data/output.txt]
    cmd: echo "hello from docker" > /workspace/data/output.txt
""")

            # Execute
            result = run_tasktree_cli(["hello"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify output
            output_file = project_root / "data" / "output.txt"
            self.assertTrue(output_file.exists(), "Output file not created")
            self.assertEqual(
                output_file.read_text().strip(),
                "hello from docker"
            )

    def test_file_creation_persists_to_host(self):
        """Test that files created in container appear on host via volume mount."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create src directory
            (project_root / "src").mkdir()

            # Create recipe
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./src:/workspace/src"]

tasks:
  generate:
    env: alpine
    outputs: [src/generated.txt]
    cmd: |
      echo "line 1" > /workspace/src/generated.txt
      echo "line 2" >> /workspace/src/generated.txt
""")

            # Execute
            result = run_tasktree_cli(["generate"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify file exists on host
            output_file = project_root / "src" / "generated.txt"
            self.assertTrue(output_file.exists(), "Generated file not found on host")

            # Verify content
            content = output_file.read_text()
            self.assertIn("line 1", content)
            self.assertIn("line 2", content)

    def test_multiline_command_execution(self):
        """Test that multi-line commands execute correctly in Docker container."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe with multi-line command
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]

tasks:
  multi:
    env: alpine
    outputs: [output/result.txt]
    cmd: |
      # This is a multi-line command
      echo "Step 1" > /workspace/output/result.txt
      echo "Step 2" >> /workspace/output/result.txt
      echo "Step 3" >> /workspace/output/result.txt
      cat /workspace/output/result.txt
""")

            # Execute
            result = run_tasktree_cli(["multi"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify output file
            output_file = project_root / "output" / "result.txt"
            self.assertTrue(output_file.exists(), "Multi-line command output not created")

            # Verify all steps executed
            content = output_file.read_text()
            self.assertIn("Step 1", content)
            self.assertIn("Step 2", content)
            self.assertIn("Step 3", content)


if __name__ == "__main__":
    unittest.main()
