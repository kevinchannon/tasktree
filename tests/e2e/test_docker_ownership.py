"""E2E tests for Docker file ownership and user mapping."""

import os
import platform
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from . import get_file_ownership, is_docker_available, run_tasktree_cli


@unittest.skipIf(platform.system() == "Windows", "User mapping not used on Windows")
class TestDockerOwnership(unittest.TestCase):
    """Test Docker user mapping and file ownership (Linux/macOS only)."""

    @classmethod
    def setUpClass(cls):
        """Ensure Docker is available before running tests."""
        if not is_docker_available():
            raise RuntimeError(
                "Docker is not available or not running. "
                "E2E tests require Docker to be installed and the daemon to be running."
            )

    def test_files_created_with_host_user_ownership(self):
        """Test that files created in container have correct host user ownership."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create data directory
            (project_root / "data").mkdir()

            # Create recipe (default run_as_root: false)
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./data:/workspace/data"]

tasks:
  create_file:
    env: alpine
    outputs: [data/owned.txt]
    cmd: echo "created by host user" > /workspace/data/owned.txt
""")

            # Execute
            result = run_tasktree_cli(["create_file"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify file ownership
            output_file = project_root / "data" / "owned.txt"
            self.assertTrue(output_file.exists(), "File not created")

            uid, gid = get_file_ownership(output_file)
            current_uid = os.getuid()
            current_gid = os.getgid()

            self.assertEqual(
                uid,
                current_uid,
                f"File owned by UID {uid}, expected {current_uid} (current user)"
            )
            self.assertEqual(
                gid,
                current_gid,
                f"File owned by GID {gid}, expected {current_gid} (current group)"
            )
            self.assertNotEqual(uid, 0, "File should NOT be owned by root")

    @unittest.skipIf(
        platform.system() == "Darwin",
        "Docker Desktop on macOS handles file ownership through VM differently"
    )
    def test_run_as_root_creates_root_owned_files(self):
        """Test that run_as_root: true creates root-owned files."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create Dockerfile
            (project_root / "Dockerfile").write_text(
                "FROM alpine:latest\nWORKDIR /workspace\n"
            )

            # Create data directory
            (project_root / "data").mkdir()

            # Create recipe with run_as_root: true
            (project_root / "tasktree.yaml").write_text("""
environments:
  alpine:
    dockerfile: ./Dockerfile
    context: .
    volumes: ["./data:/workspace/data"]
    run_as_root: true

tasks:
  create_as_root:
    env: alpine
    outputs: [data/root_owned.txt]
    cmd: echo "created by root" > /workspace/data/root_owned.txt
""")

            # Execute
            result = run_tasktree_cli(["create_as_root"], cwd=project_root)

            # Assert success
            self.assertEqual(
                result.returncode,
                0,
                f"CLI failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

            # Verify file ownership
            output_file = project_root / "data" / "root_owned.txt"
            self.assertTrue(output_file.exists(), "File not created")

            uid, gid = get_file_ownership(output_file)

            # File should be owned by root (UID 0)
            self.assertEqual(
                uid,
                0,
                f"File owned by UID {uid}, expected 0 (root) when run_as_root: true"
            )


if __name__ == "__main__":
    unittest.main()
