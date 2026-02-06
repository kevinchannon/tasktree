"""E2E tests for Docker runner configuration."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerRunner(unittest.TestCase):
    """
    Test Docker runner variable and configuration features.
    @athena: c7c662b4eea1
    """

    @classmethod
    def setUpClass(cls):
        """
        Ensure Docker is available before running tests.
        @athena: c8c40c167b6e
        """
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_environment_variable_injection(self):
        """
        Test that env_vars are passed to container correctly.
        @athena: c271cc48b3ff
        """
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
runners:
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
    run_in: alpine
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
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify environment variables were set
            env_file = project_root / "output" / "env.txt"
            self.assertTrue(env_file.exists(), "Environment check file not created")

            content = env_file.read_text()
            self.assertIn("BUILD_ENV=production", content)
            self.assertIn("VERSION=1.2.3", content)
            self.assertIn("DEBUG=false", content)

    def test_container_working_directory(self):
        """
        Test that container working_dir is set correctly.
        @athena: 79d7fac1169e
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe with working_dir in runner only
            (project_root / "tasktree.yaml").write_text("""
runners:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]
    working_dir: "/app"

tasks:
  check_pwd:
    run_in: alpine
    outputs: [output/pwd.txt]
    cmd: pwd > /workspace/output/pwd.txt
""")

            # Execute
            result = run_tasktree_cli(["check_pwd"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify working directory was set correctly
            pwd_file = project_root / "output" / "pwd.txt"
            self.assertTrue(
                pwd_file.exists(), "Working directory check file not created"
            )

            # Should be /app (runner working_dir)
            pwd = pwd_file.read_text().strip()
            self.assertEqual(pwd, "/app", f"Unexpected working directory: {pwd}")

    def test_extra_docker_args(self):
        """
        Test that extra_args are passed to docker run.
        @athena: 6b8eb410e4a4
        """
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
runners:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]
    extra_args:
      - "--memory=512m"
      - "--cpus=1"

tasks:
  limited:
    run_in: alpine
    outputs: [output/success.txt]
    cmd: echo "container ran with limits" > /workspace/output/success.txt
""")

            # Execute
            result = run_tasktree_cli(["limited"], cwd=project_root)

            # Assert success (we can't verify limits were applied, but we can verify execution succeeded)
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify task completed despite extra args
            success_file = project_root / "output" / "success.txt"
            self.assertTrue(
                success_file.exists(), "Task with extra args did not complete"
            )
            self.assertIn("container ran with limits", success_file.read_text())

    def test_dockerfile_workdir_default(self):
        """
        Test that container uses Dockerfile WORKDIR when no working_dir specified.
        @athena: e4f9a2b7c3d8
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile with non-root WORKDIR
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /app\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create recipe WITHOUT working_dir in runner or task
            (project_root / "tasktree.yaml").write_text("""
runners:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./output:/output"]

tasks:
  check_pwd:
    run_in: alpine
    outputs: [output/pwd.txt]
    cmd: pwd > /output/pwd.txt
""")

            # Execute
            result = run_tasktree_cli(["check_pwd"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify working directory matches Dockerfile WORKDIR
            pwd_file = project_root / "output" / "pwd.txt"
            self.assertTrue(
                pwd_file.exists(), "Working directory check file not created"
            )

            # Should be /app (from Dockerfile WORKDIR)
            pwd = pwd_file.read_text().strip()
            self.assertEqual(
                pwd, "/app", f"Expected /app from Dockerfile WORKDIR, got: {pwd}"
            )

    def test_config_file_with_relative_dockerfile_path(self):
        """
        Test that relative dockerfile paths in config files are parsed and resolved correctly.
        This test verifies that:
        1. Config files can contain relative paths
        2. Relative paths in recipe runners are resolved at execution time
        @athena: to-be-generated
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create docker subdirectory
            docker_dir = project_root / "docker"
            docker_dir.mkdir()

            # Create Dockerfile in subdirectory
            (docker_dir / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create output directory
            (project_root / "output").mkdir()

            # Create project config with relative dockerfile path
            # Even though we don't use this runner, this tests that the config
            # file can be parsed without errors when it contains relative paths
            (project_root / ".tasktree-config.yml").write_text("""runners:
  default:
    dockerfile: docker/Dockerfile
    context: .
""")

            # Create recipe with runner using relative paths
            # This is what actually gets executed and tests path resolution
            (project_root / "tasktree.yaml").write_text("""runners:
  docker-test:
    dockerfile: docker/Dockerfile
    context: .
    volumes: ["./output:/workspace/output"]

tasks:
  test:
    run_in: docker-test
    outputs: [output/result.txt]
    cmd: echo "path resolution works" > /workspace/output/result.txt
""")

            # Execute task
            result = run_tasktree_cli(["test"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify output file was created
            output_file = project_root / "output" / "result.txt"
            self.assertTrue(output_file.exists(), "Output file not created")
            self.assertEqual(
                output_file.read_text().strip(), "path resolution works"
            )


if __name__ == "__main__":
    unittest.main()
