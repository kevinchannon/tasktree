"""E2E tests for variable substitution in Docker runner fields.

Regression tests for issue #179: variable substitution into docker runner
fields doesn't work if the docker image needs to be built.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import is_docker_available, run_tasktree_cli


class TestDockerVariableSubstitution(unittest.TestCase):
    """
    Test that {{ var.* }} substitution works in Docker runner fields when the
    docker image needs to be built.
    """

    @classmethod
    def setUpClass(cls):
        """
        Ensure Docker is available before running tests.
        """
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_var_substitution_in_volume_when_image_needs_building(self):
        """
        Regression test for issue #179: variable substitution in docker runner
        volume fields should work even when the docker image needs to be built.

        Uses the exact task configuration from the bug report.
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile (image will need to be built from scratch)
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create a directory that will be mapped via the variable-substituted volume
            data_dir = project_root / "data"
            data_dir.mkdir()

            # Create recipe using the exact structure from the bug report,
            # but using a temp-local path for the volume so it's portable
            (project_root / "tasktree.yaml").write_text(f"""
variables:
  mount_dir: "{data_dir}"

runners:
  docker:
    dockerfile: Dockerfile
    volumes:
      - "{{{{ var.mount_dir }}}}:/a"

tasks:
  foo:
    run_in: docker
    outputs: [data/result.txt]
    cmd: "echo running > /a/result.txt"
""")

            # Execute - this should succeed with the variable substituted in the volume
            result = run_tasktree_cli(["foo"], cwd=project_root, timeout=120)

            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed with variable substitution in docker volume:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )

            # Verify the container actually ran and wrote the output
            output_file = data_dir / "result.txt"
            self.assertTrue(
                output_file.exists(),
                "Output file not created - container did not run correctly",
            )
