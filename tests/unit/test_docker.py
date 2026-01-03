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

    def test_shell_environment_with_list_args(self):
        """Test that shell environments still work with list args (backward compatibility)."""
        # Shell environments should use list args for shell arguments
        env = Environment(
            name="bash",
            shell="bash",
            args=["-c", "-e"],  # List of shell arguments
        )

        # Verify it's recognized as a shell environment (not Docker)
        self.assertFalse(is_docker_environment(env))

        # Verify args are stored as a list
        self.assertIsInstance(env.args, list)
        self.assertEqual(env.args, ["-c", "-e"])

    def test_docker_environment_with_dict_args(self):
        """Test that Docker environments use dict args for build arguments."""
        # Docker environments should use dict args for build arguments
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={"BUILD_VERSION": "1.0.0", "BUILD_DATE": "2024-01-01"},
        )

        # Verify it's recognized as a Docker environment
        self.assertTrue(is_docker_environment(env))

        # Verify args are stored as a dict
        self.assertIsInstance(env.args, dict)
        self.assertEqual(env.args, {"BUILD_VERSION": "1.0.0", "BUILD_DATE": "2024-01-01"})


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

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_with_build_args(self, mock_run):
        """Test that docker build command includes --build-arg flags."""
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={"FOO": "fooable", "bar": "you're barred!"},
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

        # Check that docker build was called with build args (2nd call, after docker --version)
        build_call_args = mock_run.call_args_list[1][0][0]

        # Verify basic command structure
        self.assertEqual(build_call_args[0], "docker")
        self.assertEqual(build_call_args[1], "build")
        self.assertEqual(build_call_args[2], "-t")
        self.assertEqual(build_call_args[3], "tt-env-builder")
        self.assertEqual(build_call_args[4], "-f")

        # Verify build args are included
        self.assertIn("--build-arg", build_call_args)

        # Find all build arg pairs
        build_args = {}
        for i, arg in enumerate(build_call_args):
            if arg == "--build-arg":
                arg_pair = build_call_args[i + 1]
                key, value = arg_pair.split("=", 1)
                build_args[key] = value

        # Verify expected build args
        self.assertEqual(build_args["FOO"], "fooable")
        self.assertEqual(build_args["bar"], "you're barred!")

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_with_empty_build_args(self, mock_run):
        """Test that docker build command works with empty build args dict."""
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={},
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

        # Check that docker build was called (2nd call, after docker --version)
        build_call_args = mock_run.call_args_list[1][0][0]

        # Verify basic command structure
        self.assertEqual(build_call_args[0], "docker")
        self.assertEqual(build_call_args[1], "build")

        # Verify NO build args are included
        self.assertNotIn("--build-arg", build_call_args)

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_with_special_characters_in_args(self, mock_run):
        """Test that build args with special characters are handled correctly."""
        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={
                "API_KEY": "sk-1234_abcd-5678",
                "MESSAGE": "Hello, World!",
                "PATH_WITH_SPACES": "/path/to/my files",
                "SPECIAL_CHARS": "test=value&foo=bar",
            },
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

        # Check that docker build was called (2nd call, after docker --version)
        build_call_args = mock_run.call_args_list[1][0][0]

        # Find all build arg pairs
        build_args = {}
        for i, arg in enumerate(build_call_args):
            if arg == "--build-arg":
                arg_pair = build_call_args[i + 1]
                key, value = arg_pair.split("=", 1)
                build_args[key] = value

        # Verify special characters are preserved
        self.assertEqual(build_args["API_KEY"], "sk-1234_abcd-5678")
        self.assertEqual(build_args["MESSAGE"], "Hello, World!")
        self.assertEqual(build_args["PATH_WITH_SPACES"], "/path/to/my files")
        self.assertEqual(build_args["SPECIAL_CHARS"], "test=value&foo=bar")

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

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_linux(self, mock_platform):
        """Test that user flag is added on Linux."""
        mock_platform.return_value = "Linux"
        self.assertTrue(self.manager._should_add_user_flag())

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_darwin(self, mock_platform):
        """Test that user flag is added on macOS."""
        mock_platform.return_value = "Darwin"
        self.assertTrue(self.manager._should_add_user_flag())

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_windows(self, mock_platform):
        """Test that user flag is NOT added on Windows."""
        mock_platform.return_value = "Windows"
        self.assertFalse(self.manager._should_add_user_flag())

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid")
    @patch("tasktree.docker.os.getgid")
    def test_run_in_container_adds_user_flag_by_default(
        self, mock_getgid, mock_getuid, mock_platform, mock_run
    ):
        """Test that --user flag is added by default on Linux."""
        mock_platform.return_value = "Linux"
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
        )

        # Find the docker run call (should be the 4th call: docker --version, build, inspect, run)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is present
        self.assertIn("--user", run_call_args)
        user_flag_index = run_call_args.index("--user")
        self.assertEqual(run_call_args[user_flag_index + 1], "1000:1000")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_skips_user_flag_on_windows(self, mock_platform, mock_run):
        """Test that --user flag is NOT added on Windows."""
        mock_platform.return_value = "Windows"

        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is NOT present
        self.assertNotIn("--user", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid")
    @patch("tasktree.docker.os.getgid")
    def test_run_in_container_respects_run_as_root_flag(
        self, mock_getgid, mock_getuid, mock_platform, mock_run
    ):
        """Test that run_as_root=True prevents --user flag from being added."""
        mock_platform.return_value = "Linux"
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        env = Environment(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
            run_as_root=True,  # Explicitly request root
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is NOT present when run_as_root=True
        self.assertNotIn("--user", run_call_args)


if __name__ == "__main__":
    unittest.main()
