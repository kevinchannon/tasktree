"""Unit tests for Docker integration."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from tasktree import docker as docker_module
from tasktree.docker import (
    DockerManager,
    check_unpinned_images,
    extract_from_images,
    is_docker_environment,
    parse_base_image_digests,
    resolve_container_working_dir,
)
from tasktree.parser import Environment


class TestExtractFromImages(unittest.TestCase):
    """Test FROM line parsing from Dockerfiles."""

    def test_simple_image(self):
        """Test simple FROM image."""
        dockerfile = "FROM python:3.11"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("python:3.11", None)])

    def test_pinned_image(self):
        """Test FROM image with digest."""
        dockerfile = "FROM rust:1.75@sha256:abc123def456"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("rust:1.75", "sha256:abc123def456")])

    def test_image_with_platform(self):
        """Test FROM with platform flag."""
        dockerfile = "FROM --platform=linux/amd64 python:3.11"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("python:3.11", None)])

    def test_image_with_alias(self):
        """Test FROM with AS alias."""
        dockerfile = "FROM rust:1.75 AS builder"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("rust:1.75", None)])

    def test_multi_stage_build(self):
        """Test multi-stage Dockerfile."""
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM debian:slim
        """
        images = extract_from_images(dockerfile)
        self.assertEqual(
            images,
            [
                ("rust:1.75", "sha256:abc123"),
                ("debian:slim", None),
            ],
        )

    def test_case_insensitive(self):
        """Test that FROM is case-insensitive."""
        dockerfile = "from python:3.11"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("python:3.11", None)])


class TestCheckUnpinnedImages(unittest.TestCase):
    """Test unpinned image detection."""

    def test_all_pinned(self):
        """Test Dockerfile with all pinned images."""
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM debian:slim@sha256:def456
        """
        unpinned = check_unpinned_images(dockerfile)
        self.assertEqual(unpinned, [])

    def test_all_unpinned(self):
        """Test Dockerfile with all unpinned images."""
        dockerfile = """
FROM python:3.11
FROM node:18
        """
        unpinned = check_unpinned_images(dockerfile)
        self.assertEqual(unpinned, ["python:3.11", "node:18"])

    def test_mixed(self):
        """Test Dockerfile with mixed pinned/unpinned."""
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM python:3.11
        """
        unpinned = check_unpinned_images(dockerfile)
        self.assertEqual(unpinned, ["python:3.11"])


class TestParseBaseImageDigests(unittest.TestCase):
    """Test base image digest parsing."""

    def test_no_digests(self):
        """Test Dockerfile with no pinned digests."""
        dockerfile = "FROM python:3.11"
        digests = parse_base_image_digests(dockerfile)
        self.assertEqual(digests, [])

    def test_single_digest(self):
        """Test Dockerfile with single digest."""
        dockerfile = "FROM python:3.11@sha256:abc123def456"
        digests = parse_base_image_digests(dockerfile)
        self.assertEqual(digests, ["sha256:abc123def456"])

    def test_multiple_digests(self):
        """Test Dockerfile with multiple digests."""
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM debian:slim@sha256:def456
        """
        digests = parse_base_image_digests(dockerfile)
        self.assertEqual(digests, ["sha256:abc123", "sha256:def456"])


class TestIsDockerEnvironment(unittest.TestCase):
    """Test Docker environment detection."""

    def test_docker_environment(self):
        """Test environment with dockerfile."""
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
        )
        self.assertTrue(is_docker_environment(env))

    def test_shell_environment(self):
        """Test environment without dockerfile."""
        env = Environment(
            name="bash",
            shell="bash",
            args=["-c"],
        )
        self.assertFalse(is_docker_environment(env))


class TestResolveContainerWorkingDir(unittest.TestCase):
    """Test container working directory resolution."""

    def test_both_specified(self):
        """Test with both env and task working dirs."""
        result = resolve_container_working_dir("/workspace", "src")
        self.assertEqual(result, "/workspace/src")

    def test_only_env_specified(self):
        """Test with only env working dir."""
        result = resolve_container_working_dir("/workspace", "")
        self.assertEqual(result, "/workspace")

    def test_only_task_specified(self):
        """Test with only task working dir."""
        result = resolve_container_working_dir("", "src")
        self.assertEqual(result, "/src")

    def test_neither_specified(self):
        """Test with neither specified."""
        result = resolve_container_working_dir("", "")
        self.assertEqual(result, "/")

    def test_path_normalization(self):
        """Test that paths are normalized."""
        result = resolve_container_working_dir("/workspace/", "/src/")
        # Trailing slashes are handled, result has trailing slash from task dir
        self.assertEqual(result, "/workspace/src/")


class TestDockerManager(unittest.TestCase):
    """Test DockerManager class."""

    def setUp(self):
        """Set up test environment."""
        self.project_root = Path("/fake/project")
        self.manager = DockerManager(self.project_root)

    @patch("tasktree.docker.subprocess.run")
    def test_ensure_image_built_caching(self, mock_run):
        """Test that images are cached per invocation."""
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
        )

        # Mock successful build and docker --version check and docker inspect
        # docker --version, docker build, docker inspect
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                # Mock docker inspect returning image ID
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect

        # First call should check docker, build, and inspect
        tag1, image_id1 = self.manager.ensure_image_built(env)
        self.assertEqual(tag1, "tt-env-builder")
        self.assertEqual(image_id1, "sha256:abc123def456")
        # Should have called docker --version, docker build, and docker inspect
        self.assertEqual(mock_run.call_count, 3)

        # Second call should use cache (no additional docker build)
        tag2, image_id2 = self.manager.ensure_image_built(env)
        self.assertEqual(tag2, "tt-env-builder")
        self.assertEqual(image_id2, "sha256:abc123def456")
        self.assertEqual(mock_run.call_count, 3)  # No additional calls

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_structure(self, mock_run):
        """Test that docker build command is structured correctly."""
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
        )

        # Mock docker inspect returning image ID
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect

        self.manager.ensure_image_built(env)

        # Check that docker build was called with correct args (2nd call, after docker --version)
        build_call_args = mock_run.call_args_list[1][0][0]
        self.assertEqual(build_call_args[0], "docker")
        self.assertEqual(build_call_args[1], "build")
        self.assertEqual(build_call_args[2], "-t")
        self.assertEqual(build_call_args[3], "tt-env-builder")
        self.assertEqual(build_call_args[4], "-f")

    def test_resolve_volume_mount_relative(self):
        """Test relative volume path resolution."""
        volume = "./src:/workspace/src"
        resolved = self.manager._resolve_volume_mount(volume)
        expected = f"{self.project_root / 'src'}:/workspace/src"
        self.assertEqual(resolved, expected)

    def test_resolve_volume_mount_absolute(self):
        """Test absolute volume path resolution."""
        volume = "/absolute/path:/container/path"
        resolved = self.manager._resolve_volume_mount(volume)
        self.assertEqual(resolved, "/absolute/path:/container/path")

    @patch("tasktree.docker.os.path.expanduser")
    def test_resolve_volume_mount_home(self, mock_expanduser):
        """Test home directory expansion in volume paths."""
        mock_expanduser.return_value = "/home/user/.cargo"
        volume = "~/.cargo:/root/.cargo"
        resolved = self.manager._resolve_volume_mount(volume)
        self.assertEqual(resolved, "/home/user/.cargo:/root/.cargo")

    def test_resolve_volume_mount_invalid(self):
        """Test invalid volume specification."""
        with self.assertRaises(ValueError):
            self.manager._resolve_volume_mount("invalid-no-colon")


if __name__ == "__main__":
    unittest.main()
