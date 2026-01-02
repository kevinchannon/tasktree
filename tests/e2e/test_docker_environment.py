"""E2E tests for Docker environment configuration."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerEnvironment(unittest.TestCase):
    """Test Docker environment variable and configuration features."""

    @classmethod
    def setUpClass(cls):
        """Ensure Docker is available before running tests."""
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_environment_variable_injection(self):
        """Test that env_vars are passed to container correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe with environment variables
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]
    env_vars:
      BUILD_ENV: "production"
      VERSION: "1.2.3"
      DEBUG: "false"

tasks:
  check_env:
    env: alpine
    outputs: [output/env.txt]
    cmd: |
      echo "BUILD_ENV=$BUILD_ENV" > /workspace/output/env.txt
      echo "VERSION=$VERSION" >> /workspace/output/env.txt
      echo "DEBUG=$DEBUG" >> /workspace/output/env.txt
""")

            # Execute
            result = run_tasktree_cli(["check_env"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify environment variables were set
            env_file = project_root / "output" / "env.txt"
            self.assertTrue(env_file.exists(), "Environment check file not created")

            content = env_file.read_text()
            self.assertIn("BUILD_ENV=production", content)
            self.assertIn("VERSION=1.2.3", content)
            self.assertIn("DEBUG=false", content)

    def test_container_working_directory(self):
        """Test that container working_dir is set correctly."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe with working_dir in environment only
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]
    working_dir: "/app"

tasks:
  check_pwd:
    env: alpine
    outputs: [output/pwd.txt]
    cmd: pwd > /workspace/output/pwd.txt
""")

            # Execute
            result = run_tasktree_cli(["check_pwd"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify working directory was set correctly
            pwd_file = project_root / "output" / "pwd.txt"
            self.assertTrue(pwd_file.exists(), "Working directory check file not created")

            # Should be /app (env working_dir)
            pwd = pwd_file.read_text().strip()
            self.assertEqual(pwd, "/app", f"Unexpected working directory: {pwd}")

    def test_extra_docker_args(self):
        """Test that extra_args are passed to docker run."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe with extra docker args
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]
    extra_args:
      - "--memory=512m"
      - "--cpus=1"

tasks:
  limited:
    env: alpine
    outputs: [output/success.txt]
    cmd: echo "container ran with limits" > /workspace/output/success.txt
""")

            # Execute
            result = run_tasktree_cli(["limited"], cwd=project_root)

            # Assert success (we can't verify limits were applied, but we can verify execution succeeded)
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify task completed despite extra args
            success_file = project_root / "output" / "success.txt"
            self.assertTrue(success_file.exists(), "Task with extra args did not complete")
            self.assertIn("container ran with limits", success_file.read_text())


if __name__ == "__main__":
    unittest.main()
