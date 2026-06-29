"""Integration tests for Docker script execution with TempScript."""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from typer.testing import CliRunner

from helpers.docker import is_docker_available
from tasktree.cli import app


class TestDockerScriptExecution(unittest.TestCase):
    """
    Test Docker script execution with TempScript context manager.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.runner = CliRunner()
        self.env = {"NO_COLOR": "1"}

    @unittest.skipUnless(is_docker_available(), "Docker not available")
    def test_docker_executes_multiline_script(self):
        """
        A Docker runner with an explicit interpreter runs a multi-line script.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "output").mkdir()

            dockerfile = project_root / "Dockerfile"
            dockerfile.write_text("""FROM alpine:latest
WORKDIR /workspace
""")

            recipe_file = project_root / "tasktree.yaml"
            recipe_file.write_text("""
runners:
  default: builder
  builder:
    dockerfile: ./Dockerfile
    context: .
    interpreter: sh
    volumes: ["./output:/workspace/output"]

tasks:
  build:
    run_in: builder
    outputs: [output/first.txt, output/second.txt]
    cmd: |
      echo "first" > output/first.txt
      echo "second" > output/second.txt
""")

            original_cwd = os.getcwd()
            try:
                os.chdir(project_root)

                result = self.runner.invoke(app, ["build"], env=self.env)
                self.assertEqual(
                    result.exit_code, 0,
                    f"Task failed:\n{result.stdout}\n{result.stderr}",
                )

                first = project_root / "output" / "first.txt"
                second = project_root / "output" / "second.txt"
                self.assertTrue(first.exists() and second.exists())
                self.assertIn("first", first.read_text())
                self.assertIn("second", second.read_text())
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
