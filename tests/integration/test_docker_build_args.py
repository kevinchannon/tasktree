"""Integration tests for Docker build args functionality."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from helpers.docker import is_docker_available
from tasktree.cli import app


class TestDockerBuildArgs(unittest.TestCase):
    """
    Test Docker build args are passed correctly to docker build.
    @athena: 3788b22a1d83
    """

    def setUp(self):
        """
        Set up test fixtures.
        @athena: 36a706d60319
        """
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    @unittest.skipUnless(is_docker_available(), "Docker not available")
    def test_build_args_passed_to_dockerfile(self):
        """
        Test that build args are passed to docker build and used in Dockerfile.
        @athena: 5ae4d329e037
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create a Dockerfile that uses ARG statements
            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""FROM alpine:latest

ARG BUILD_VERSION
ARG BUILD_DATE
ARG PYTHON_VERSION=3.11

RUN echo "Build version: $BUILD_VERSION" > /build-info.txt && \\
    echo "Build date: $BUILD_DATE" >> /build-info.txt && \\
    echo "Python version: $PYTHON_VERSION" >> /build-info.txt

CMD ["sh", "-c", "cat /build-info.txt"]
""")

            # Create recipe with Docker runner and build args
            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  default: builder
  builder:
    dockerfile: ./Dockerfile
    context: .
    args:
      BUILD_VERSION: "1.2.3"
      BUILD_DATE: "2024-01-01"
      PYTHON_VERSION: "3.12"

tasks:
  build:
    run_in: builder
    outputs: [build-output.txt]
    cmd: cat /build-info.txt > build-output.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                # Run the task - this will build the Docker image with build args
                # Note: This test will be skipped in CI if Docker is not available
                result = self.runner.invoke(app, ["build"], env=self.env)

                self.assertEqual(result.exit_code, 0, f"Task failed:\n{result.stdout}\n{result.stderr}")

                # Verify that the build args were actually used in the container
                build_output = project_root / "build-output.txt"
                self.assertTrue(build_output.exists(), "build-output.txt should be created")

                content = build_output.read_text()
                self.assertIn("Build version: 1.2.3", content, "BUILD_VERSION arg should be passed")
                self.assertIn("Build date: 2024-01-01", content, "BUILD_DATE arg should be passed")
                self.assertIn("Python version: 3.12", content, "PYTHON_VERSION arg should override default")

            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
