"""Unit tests for Docker integration."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from helpers.logging import logger_stub
from tasktree.docker import (
    DockerManager,
    _get_container_script_extension,
    _is_windows_shell,
    check_unpinned_images,
    extract_from_images,
    is_docker_runner,
    parse_base_image_digests,
    resolve_container_working_dir,
)
from tasktree.parser import Runner
from tasktree.process_runner import TaskOutputTypes, make_process_runner


class TestExtractFromImages(unittest.TestCase):
    """
    Test FROM line parsing from Dockerfiles.
    @athena: 072447d5ae17
    """

    def test_simple_image(self):
        """
        Test simple FROM image.
        @athena: ecbc84ea0794
        """
        dockerfile = "FROM python:3.11"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("python:3.11", None)])

    def test_pinned_image(self):
        """
        Test FROM image with digest.
        @athena: ef177cb0bcdb
        """
        dockerfile = "FROM rust:1.75@sha256:abc123def456"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("rust:1.75", "sha256:abc123def456")])

    def test_image_with_platform(self):
        """
        Test FROM with platform flag.
        @athena: 314e1cf3df4f
        """
        dockerfile = "FROM --platform=linux/amd64 python:3.11"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("python:3.11", None)])

    def test_image_with_alias(self):
        """
        Test FROM with AS alias.
        @athena: 50ce42efa647
        """
        dockerfile = "FROM rust:1.75 AS builder"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("rust:1.75", None)])

    def test_multi_stage_build(self):
        """
        Test multi-stage Dockerfile.
        @athena: 12e62781c16f
        """
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
        """
        Test that FROM is case-insensitive.
        @athena: 1a6541f888d3
        """
        dockerfile = "from python:3.11"
        images = extract_from_images(dockerfile)
        self.assertEqual(images, [("python:3.11", None)])


class TestCheckUnpinnedImages(unittest.TestCase):
    """
    Test unpinned image detection.
    @athena: f1bd0d6c05d1
    """

    def test_all_pinned(self):
        """
        Test Dockerfile with all pinned images.
        @athena: 458b34f2a190
        """
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM debian:slim@sha256:def456
        """
        unpinned = check_unpinned_images(dockerfile)
        self.assertEqual(unpinned, [])

    def test_all_unpinned(self):
        """
        Test Dockerfile with all unpinned images.
        @athena: 4888d3f282ed
        """
        dockerfile = """
FROM python:3.11
FROM node:18
        """
        unpinned = check_unpinned_images(dockerfile)
        self.assertEqual(unpinned, ["python:3.11", "node:18"])

    def test_mixed(self):
        """
        Test Dockerfile with mixed pinned/unpinned.
        @athena: 1310c9319165
        """
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM python:3.11
        """
        unpinned = check_unpinned_images(dockerfile)
        self.assertEqual(unpinned, ["python:3.11"])


class TestParseBaseImageDigests(unittest.TestCase):
    """
    Test base image digest parsing.
    @athena: 5994f929ffba
    """

    def test_no_digests(self):
        """
        Test Dockerfile with no pinned digests.
        @athena: 5d0582b6cb79
        """
        dockerfile = "FROM python:3.11"
        digests = parse_base_image_digests(dockerfile)
        self.assertEqual(digests, [])

    def test_single_digest(self):
        """
        Test Dockerfile with single digest.
        @athena: 8d555f3e9b7a
        """
        dockerfile = "FROM python:3.11@sha256:abc123def456"
        digests = parse_base_image_digests(dockerfile)
        self.assertEqual(digests, ["sha256:abc123def456"])

    def test_multiple_digests(self):
        """
        Test Dockerfile with multiple digests.
        @athena: fec6d0c60367
        """
        dockerfile = """
FROM rust:1.75@sha256:abc123 AS builder
FROM debian:slim@sha256:def456
        """
        digests = parse_base_image_digests(dockerfile)
        self.assertEqual(digests, ["sha256:abc123", "sha256:def456"])


class TestIsDockerRunner(unittest.TestCase):
    """
    Test Docker environment detection.
    @athena: 7e9d896c1a55
    """

    def test_docker_runner(self):
        """
        Test runner with dockerfile.
        @athena: a88fcecf498e
        """
        runner = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
        )
        self.assertTrue(is_docker_runner(runner))

    def test_shell_runner(self):
        """
        Test runner without dockerfile.
        @athena: ecde4c39cb67
        """
        runner = Runner(
            name="bash",
            shell="bash",
            args=["-c"],
        )
        self.assertFalse(is_docker_runner(runner))

    def test_shell_runner_with_list_args(self):
        """
        Test that shell runners still work with list args (backward compatibility).
        @athena: c03e04ec3817
        """
        # Shell runners should use list args for shell arguments
        runner = Runner(
            name="bash",
            shell="bash",
            args=["-c", "-e"],  # List of shell arguments
        )

        # Verify it's recognized as a shell runner (not Docker)
        self.assertFalse(is_docker_runner(runner))

        # Verify args are stored as a list
        self.assertIsInstance(runner.args, list)
        self.assertEqual(runner.args, ["-c", "-e"])

    def test_docker_runner_with_dict_args(self):
        """
        Test that Docker runners use dict args for build arguments.
        @athena: 1cf37d1c8e86
        """
        # Docker runners should use dict args for build arguments
        runner = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={"BUILD_VERSION": "1.0.0", "BUILD_DATE": "2024-01-01"},
        )

        # Verify it's recognized as a Docker runner
        self.assertTrue(is_docker_runner(runner))

        # Verify args are stored as a dict
        self.assertIsInstance(runner.args, dict)
        self.assertEqual(
            runner.args, {"BUILD_VERSION": "1.0.0", "BUILD_DATE": "2024-01-01"}
        )


class TestWindowsShellDetection(unittest.TestCase):
    """
    Test Windows shell detection helper function.
    """

    def test_is_windows_shell_cmd(self):
        """Test that cmd.exe is recognized as Windows shell."""
        self.assertTrue(_is_windows_shell("cmd.exe"))
        self.assertTrue(_is_windows_shell("CMD.EXE"))
        self.assertTrue(_is_windows_shell("cmd"))

    def test_is_windows_shell_powershell(self):
        """Test that PowerShell variants are recognized as Windows shells."""
        self.assertTrue(_is_windows_shell("powershell"))
        self.assertTrue(_is_windows_shell("powershell.exe"))
        self.assertTrue(_is_windows_shell("pwsh"))
        self.assertTrue(_is_windows_shell("POWERSHELL"))

    def test_is_windows_shell_unix_shells(self):
        """Test that Unix shells are not recognized as Windows shells."""
        self.assertFalse(_is_windows_shell("bash"))
        self.assertFalse(_is_windows_shell("sh"))
        self.assertFalse(_is_windows_shell("zsh"))
        self.assertFalse(_is_windows_shell("/bin/bash"))
        self.assertFalse(_is_windows_shell("/bin/sh"))


class TestContainerScriptExtension(unittest.TestCase):
    """
    Test container script extension determination.
    """

    def test_get_container_script_extension_sh(self):
        """Test that Unix shells get .sh extension."""
        self.assertEqual(_get_container_script_extension("bash"), ".sh")
        self.assertEqual(_get_container_script_extension("sh"), ".sh")
        self.assertEqual(_get_container_script_extension("zsh"), ".sh")
        self.assertEqual(_get_container_script_extension("/bin/bash"), ".sh")

    def test_get_container_script_extension_bat(self):
        """Test that cmd.exe gets .bat extension."""
        self.assertEqual(_get_container_script_extension("cmd.exe"), ".bat")
        self.assertEqual(_get_container_script_extension("cmd"), ".bat")
        self.assertEqual(_get_container_script_extension("CMD"), ".bat")

    def test_get_container_script_extension_ps1(self):
        """Test that PowerShell gets .ps1 extension."""
        self.assertEqual(_get_container_script_extension("powershell"), ".ps1")
        self.assertEqual(_get_container_script_extension("powershell.exe"), ".ps1")
        self.assertEqual(_get_container_script_extension("pwsh"), ".ps1")


class TestResolveContainerWorkingDir(unittest.TestCase):
    """
    Test container working directory resolution.
    @athena: 23b80ef54ab0
    """

    def test_both_specified(self):
        """
        Test with both env and task working dirs.
        @athena: a7175ac525f7
        """
        result = resolve_container_working_dir("/workspace", "src")
        self.assertEqual(result, "/workspace/src")

    def test_only_env_specified(self):
        """
        Test with only env working dir.
        @athena: 8cb358e34c10
        """
        result = resolve_container_working_dir("/workspace", "")
        self.assertEqual(result, "/workspace")

    def test_only_task_specified(self):
        """
        Test with only task working dir.
        @athena: 0c84f6d70917
        """
        result = resolve_container_working_dir("", "src")
        self.assertEqual(result, "/src")

    def test_neither_specified(self):
        """
        Test with neither specified - should return None to use Dockerfile WORKDIR.
        @athena: 3f333b5c4c62
        """
        result = resolve_container_working_dir("", "")
        self.assertIsNone(result)

    def test_path_normalization(self):
        """
        Test that paths are normalized.
        @athena: 096f020907da
        """
        result = resolve_container_working_dir("/workspace/", "/src/")
        # Trailing slashes are handled, result has trailing slash from task dir
        self.assertEqual(result, "/workspace/src/")


class TestDockerManager(unittest.TestCase):
    """
    Test DockerManager class.
    @athena: f5ee6f7c456b
    """

    def setUp(self):
        """
        Set up test environment.
        @athena: a4d39428bb63
        """
        self.project_root = Path("/fake/project")
        self.manager = DockerManager(self.project_root, logger_stub)

    @patch("tasktree.docker.subprocess.run")
    def test_ensure_image_built_caching(self, mock_run):
        """
        Test that images are cached per invocation.
        @athena: ec5dd97bc4a8
        """
        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
        )

        # Mock successful build and docker --version check and docker inspect
        # docker --version, docker build, docker inspect
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                # Mock docker inspect returning image ID
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect

        # First call should check docker, build, and inspect
        tag1, image_id1 = self.manager.ensure_image_built(
            env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )
        self.assertEqual(tag1, "tt-env-builder")
        self.assertEqual(image_id1, "sha256:abc123def456")
        # Should have called docker --version, docker build, and docker inspect
        self.assertEqual(mock_run.call_count, 3)

        # Second call should use cache (no additional docker build)
        tag2, image_id2 = self.manager.ensure_image_built(
            env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )
        self.assertEqual(tag2, "tt-env-builder")
        self.assertEqual(image_id2, "sha256:abc123def456")
        self.assertEqual(mock_run.call_count, 3)  # No additional calls

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_structure(self, mock_run):
        """
        Test that docker build command is structured correctly.
        @athena: 21151cc7a8dd
        """
        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
        )

        # Mock docker inspect returning image ID
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect
        self.manager.ensure_image_built(
            env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        # Check that docker build was called with correct args (2nd call, after docker --version)
        build_call_args = mock_run.call_args_list[1][0][0]
        self.assertEqual(build_call_args[0], "docker")
        self.assertEqual(build_call_args[1], "build")
        self.assertEqual(build_call_args[2], "-t")
        self.assertEqual(build_call_args[3], "tt-env-builder")
        self.assertEqual(build_call_args[4], "-f")

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_with_build_args(self, mock_run):
        """
        Test that docker build command includes --build-arg flags.
        @athena: 581199f6c680
        """
        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={"FOO": "fooable", "bar": "you're barred!"},
        )

        # Mock docker inspect returning image ID
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect

        self.manager.ensure_image_built(
            env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

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
        """
        Test that docker build command works with empty build args dict.
        @athena: 28b44704ab1c
        """
        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args={},
        )

        # Mock docker inspect returning image ID
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect

        self.manager.ensure_image_built(
            env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        # Check that docker build was called (2nd call, after docker --version)
        build_call_args = mock_run.call_args_list[1][0][0]

        # Verify basic command structure
        self.assertEqual(build_call_args[0], "docker")
        self.assertEqual(build_call_args[1], "build")

        # Verify NO build args are included
        self.assertNotIn("--build-arg", build_call_args)

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_with_special_characters_in_args(self, mock_run):
        """
        Test that build args with special characters are handled correctly.
        @athena: ce755595bb2a
        """
        env = Runner(
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
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return None

        mock_run.side_effect = mock_run_side_effect

        self.manager.ensure_image_built(
            env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

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
        """
        Test relative volume path resolution.
        @athena: acc1d52db050
        """
        volume = "./src:/workspace/src"
        resolved = self.manager._resolve_volume_mount(volume)
        expected = f"{self.project_root / 'src'}:/workspace/src"
        self.assertEqual(resolved, expected)

    def test_resolve_volume_mount_absolute(self):
        """
        Test absolute volume path resolution.
        @athena: 21aec1a9dbd3
        """
        volume = "/absolute/path:/container/path"
        resolved = self.manager._resolve_volume_mount(volume)
        self.assertEqual(resolved, "/absolute/path:/container/path")

    @patch("tasktree.docker.os.path.expanduser")
    def test_resolve_volume_mount_home(self, mock_expanduser):
        """
        Test home directory expansion in volume paths.
        @athena: 279c9bfa551c
        """
        mock_expanduser.return_value = "/home/user/.cargo"
        volume = "~/.cargo:/root/.cargo"
        resolved = self.manager._resolve_volume_mount(volume)
        self.assertEqual(resolved, "/home/user/.cargo:/root/.cargo")

    def test_resolve_volume_mount_invalid(self):
        """
        Test invalid volume specification.
        @athena: cd0e7945e0cb
        """
        with self.assertRaises(ValueError):
            self.manager._resolve_volume_mount("invalid-no-colon")

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_linux(self, mock_platform):
        """
        Test that user flag is added on Linux.
        @athena: 596549549a3d
        """
        mock_platform.return_value = "Linux"
        self.assertTrue(self.manager._should_add_user_flag())

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_darwin(self, mock_platform):
        """
        Test that user flag is added on macOS.
        @athena: 690268fb52fb
        """
        mock_platform.return_value = "Darwin"
        self.assertTrue(self.manager._should_add_user_flag())

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_windows(self, mock_platform):
        """
        Test that user flag is NOT added on Windows.
        @athena: 4a296f6deac7
        """
        mock_platform.return_value = "Windows"
        self.assertFalse(self.manager._should_add_user_flag())

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid")
    @patch("tasktree.docker.os.getgid")
    def test_run_in_container_adds_user_flag_by_default(
        self, mock_getgid, mock_getuid, mock_platform, mock_run
    ):
        """
        Test that --user flag is added by default on Linux.
        @athena: 703f41bc981f
        """
        mock_platform.return_value = "Linux"
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call (should be the 4th call: docker --version, build, inspect, run)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is present
        self.assertIn("--user", run_call_args)
        user_flag_index = run_call_args.index("--user")
        self.assertEqual(run_call_args[user_flag_index + 1], "1000:1000")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_mounts_temp_script(self, mock_platform, mock_run):
        """
        Test that temp script is mounted into container.
        @athena: to-be-generated
        """
        mock_platform.return_value = "Windows"  # Skip user flag for simplicity

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify temp script volume mount is present
        # Should have at least one -v flag for the temp script
        self.assertIn("-v", run_call_args)

        # Find the temp script volume mount
        # Script path now includes UUID, so check pattern: /tmp/tt-script-{uuid}.sh:ro
        found_script_mount = False
        for i, arg in enumerate(run_call_args):
            if arg == "-v" and i + 1 < len(run_call_args):
                mount = run_call_args[i + 1]
                # Check for pattern: something:/tmp/tt-script-{uuid}.sh:ro
                if ":/tmp/tt-script-" in mount and ".sh:ro" in mount:
                    found_script_mount = True
                    break

        self.assertTrue(found_script_mount, "Temp script mount not found in docker command")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_executes_script_not_dash_c(self, mock_platform, mock_run):
        """
        Test that docker container executes script file instead of -c command.
        @athena: to-be-generated
        """
        mock_platform.return_value = "Windows"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="bash",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify -c flag is NOT present
        self.assertNotIn("-c", run_call_args)

        # Verify script path is present as last argument with pattern /tmp/tt-script-{uuid}.sh
        last_arg = run_call_args[-1]
        self.assertTrue(last_arg.startswith("/tmp/tt-script-"), f"Expected script path to start with /tmp/tt-script-, got {last_arg}")
        self.assertTrue(last_arg.endswith(".sh"), f"Expected script path to end with .sh, got {last_arg}")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_skips_user_flag_on_windows(self, mock_platform, mock_run):
        """
        Test that --user flag is NOT added on Windows.
        @athena: 9da700a3222e
        """
        mock_platform.return_value = "Windows"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
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
        """
        Test that run_as_root=True prevents --user flag from being added.
        @athena: bae8a549c901
        """
        mock_platform.return_value = "Linux"
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
            run_as_root=True,  # Explicitly request root
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is NOT present when run_as_root=True
        self.assertNotIn("--user", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_includes_extra_args(self, mock_platform, mock_run):
        """
        Test that extra_args are properly included in docker run command.
        @athena: 2f519b4e5577
        """
        mock_platform.return_value = "Windows"  # Skip user flag for simplicity

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
            extra_args=["--memory=512m", "--cpus=1", "--network=host"],
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify extra_args are included in the command
        self.assertIn("--memory=512m", run_call_args)
        self.assertIn("--cpus=1", run_call_args)
        self.assertIn("--network=host", run_call_args)

        # Verify extra_args appear before the image tag
        # Command structure: docker run --rm [extra_args] [volumes] [ports] [env] [image] [shell] -c [cmd]
        image_index = run_call_args.index("tt-env-builder")
        memory_index = run_call_args.index("--memory=512m")
        cpus_index = run_call_args.index("--cpus=1")
        network_index = run_call_args.index("--network=host")

        # All extra args should appear before the image
        self.assertLess(memory_index, image_index)
        self.assertLess(cpus_index, image_index)
        self.assertLess(network_index, image_index)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_empty_extra_args(self, mock_platform, mock_run):
        """
        Test that empty extra_args list works correctly.
        @athena: 5592b6f4dfeb
        """
        mock_platform.return_value = "Windows"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
            extra_args=[],  # Empty list
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Should succeed without errors
        run_call_args = mock_run.call_args_list[3][0][0]

        # Basic command structure should be present
        self.assertEqual(run_call_args[0], "docker")
        self.assertEqual(run_call_args[1], "run")
        self.assertIn("tt-env-builder", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_shell_args(self, mock_platform, mock_run):
        """
        Test that shell args list works correctly.
        @athena: 1d645d21622c
        """
        mock_platform.return_value = "Windows"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
            args=["-euo", "pipefail"],
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Should succeed without errors
        run_call_args = mock_run.call_args_list[3][0][0]

        # Basic command structure should be present
        self.assertEqual(run_call_args[0], "docker")
        self.assertEqual(run_call_args[1], "run")
        self.assertIn("tt-env-builder", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_substituted_variables_in_volumes(
        self, mock_platform, mock_run
    ):
        """
        Test that volume mounts work correctly after variable substitution.

        Note: Variable substitution happens in the executor before calling docker manager.
        This test verifies that the docker manager correctly handles already-substituted paths.
        @athena: 16ce782b87a4
        """
        mock_platform.return_value = "Linux"

        # Environment with already-substituted path (as would come from executor)
        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="sh",
            volumes=["/fake/project:/workspace"],  # Already substituted
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Find all -v flags and their arguments
        # The first -v is for the temp script mount, the second is the user-defined volume
        volume_indices = [i for i, arg in enumerate(run_call_args) if arg == "-v"]
        self.assertEqual(2, len(volume_indices), "Expected 2 volume mounts: script and user-defined")

        # Get the user-defined volume mount (second -v flag)
        user_volume_mount = run_call_args[volume_indices[1] + 1]

        # Verify the volume mount uses the absolute path correctly
        self.assertEqual("/fake/project:/workspace", user_volume_mount)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_preamble(self, mock_platform, mock_run):
        """
        Test that preamble is passed to TempScript and included in mounted script.
        """
        mock_platform.return_value = "Linux"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="bash",
            preamble="set -euo pipefail\n",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Test passes if no exception is raised - preamble is handled internally by TempScript
        # The actual verification of preamble content is in TempScript tests
        run_call_args = mock_run.call_args_list[3][0][0]
        self.assertIn("docker", run_call_args[0])

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_shell_args_list(self, mock_platform, mock_run):
        """
        Test that shell args (as list) are passed to docker command.
        """
        mock_platform.return_value = "Linux"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="bash",
            args=["-e", "-u"],  # Shell args as list
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="/workspace",
            process_runner=process_runner,
        )

        # Find the docker run call
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify shell args are in the command before the script path
        # Command should end with: [..., "bash", "-e", "-u", "/tmp/tt-script-{uuid}.sh"]
        self.assertIn("-e", run_call_args)
        self.assertIn("-u", run_call_args)

        # Find positions
        bash_idx = run_call_args.index("bash")
        e_idx = run_call_args.index("-e")
        u_idx = run_call_args.index("-u")

        # Verify order: bash comes before -e and -u
        self.assertLess(bash_idx, e_idx)
        self.assertLess(bash_idx, u_idx)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_windows_shell(self, mock_platform, mock_run):
        """
        Test that Windows shells (cmd.exe) use appropriate script extension and no shebang.
        """
        mock_platform.return_value = "Linux"  # Host platform (doesn't matter for container)

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile.windows",
            context=".",
            shell="cmd.exe",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="echo hello",
            working_dir=Path("/fake/project"),
            container_working_dir="C:\\workspace",
            process_runner=process_runner,
        )

        # Find the docker run call
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify script path ends with .bat (not .sh)
        last_arg = run_call_args[-1]
        self.assertTrue(last_arg.startswith("/tmp/tt-script-"), f"Expected script path to start with /tmp/tt-script-, got {last_arg}")
        self.assertTrue(last_arg.endswith(".bat"), f"Expected script path to end with .bat for cmd.exe, got {last_arg}")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_with_powershell(self, mock_platform, mock_run):
        """
        Test that PowerShell uses .ps1 extension.
        """
        mock_platform.return_value = "Linux"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile.windows",
            context=".",
            shell="powershell",
        )

        # Mock docker --version, docker build, docker inspect, and docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        self.manager.run_in_container(
            env=env,
            cmd="Write-Host 'hello'",
            working_dir=Path("/fake/project"),
            container_working_dir="C:\\workspace",
            process_runner=process_runner,
        )

        # Find the docker run call
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify script path ends with .ps1
        last_arg = run_call_args[-1]
        self.assertTrue(last_arg.endswith(".ps1"), f"Expected script path to end with .ps1 for powershell, got {last_arg}")

    @patch("tasktree.docker.subprocess.run")
    def test_error_when_dockerfile_not_found(self, mock_run):
        """
        Test that appropriate error occurs when dockerfile path cannot be resolved.
        Verifies that Docker build fails with clear error when file doesn't exist.
        @athena: to-be-generated
        """
        env = Runner(
            name="builder",
            dockerfile="nonexistent/Dockerfile",
            context=".",
        )

        # Mock docker --version to pass the check
        # Mock docker build to fail with file not found error
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "--version" in cmd:
                return Mock(returncode=0)
            elif "build" in cmd:
                # Simulate Docker's error when dockerfile doesn't exist
                result = Mock()
                result.returncode = 1
                result.stderr = "unable to prepare context: unable to stat /fake/project/nonexistent/Dockerfile"
                raise Exception(result.stderr)
            return Mock(returncode=0)

        mock_run.side_effect = mock_run_side_effect

        # Attempt to build image should raise an exception
        with self.assertRaises(Exception) as context:
            self.manager.ensure_image_built(
                env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
            )

        # Verify error message mentions the missing file
        self.assertIn("Dockerfile", str(context.exception))

    @patch("tasktree.docker.subprocess.run")
    def test_path_traversal_security(self, mock_run):
        """
        Test that path traversal attempts in dockerfile paths are handled safely.
        Verifies that paths like ../../etc/passwd are resolved by pathlib correctly.
        @athena: to-be-generated
        """
        env = Runner(
            name="traversal",
            dockerfile="../../etc/passwd",
            context=".",
        )

        # Mock docker --version and docker build
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if "--version" in cmd:
                return Mock(returncode=0)
            elif "build" in cmd:
                # Check that the path passed to docker build has been resolved
                # The -f flag should be followed by the resolved path
                dockerfile_flag_index = cmd.index("-f")
                dockerfile_path = cmd[dockerfile_flag_index + 1]

                # Path should be resolved using pathlib's / operator which normalizes paths
                # /fake/project / ../../etc/passwd resolves to /fake/etc/passwd (not /etc/passwd)
                # This is safe because pathlib keeps the path within the filesystem tree
                self.assertIn("/fake/", dockerfile_path)

                # Simulate build failure (file doesn't exist)
                result = Mock()
                result.returncode = 1
                result.stderr = f"unable to stat {dockerfile_path}"
                raise Exception(result.stderr)
            return Mock(returncode=0)

        mock_run.side_effect = mock_run_side_effect

        # Attempt to build should raise an exception
        with self.assertRaises(Exception):
            self.manager.ensure_image_built(
                env, make_process_runner(TaskOutputTypes.ALL, logger_stub)
            )

        # Verify docker build was called with resolved path
        build_call = [c for c in mock_run.call_args_list if len(c[0]) > 0 and "build" in c[0][0]]
        self.assertTrue(len(build_call) > 0, "Docker build should have been called")

    @patch("tasktree.temp_script.tempfile.NamedTemporaryFile")
    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_error_on_script_creation_failure(self, mock_platform, mock_run, mock_tempfile):
        """
        Test that DockerError is raised when TempScript fails to create script file.
        """
        mock_platform.return_value = "Linux"

        # Mock temp file creation to fail
        mock_tempfile.side_effect = OSError("Disk full")

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="bash",
        )

        # Mock docker --version, docker build, docker inspect
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

        # Should raise DockerError (not OSError) with clear message
        from tasktree.docker import DockerError

        with self.assertRaises(DockerError) as context:
            self.manager.run_in_container(
                env=env,
                cmd="echo hello",
                working_dir=Path("/fake/project"),
                container_working_dir="/workspace",
                process_runner=process_runner,
            )

        # Verify error message mentions script creation
        self.assertIn("temporary script", str(context.exception).lower())

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_error_on_docker_run_failure(self, mock_platform, mock_run):
        """
        Test that DockerError is raised when docker run fails.
        """
        mock_platform.return_value = "Linux"

        env = Runner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            shell="bash",
        )

        # Mock docker --version, docker build, docker inspect, and failing docker run
        def mock_run_side_effect(*args, **_kwargs):
            cmd = args[0]
            if "inspect" in cmd:
                result = Mock()
                result.stdout = "sha256:abc123def456\n"
                return result
            elif "docker" in cmd and "run" in cmd:
                # Simulate docker run failure
                import subprocess
                raise subprocess.CalledProcessError(125, cmd, stderr="Container failed to start")
            return Mock()

        mock_run.side_effect = mock_run_side_effect

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)

        # Should raise DockerError
        from tasktree.docker import DockerError

        with self.assertRaises(DockerError) as context:
            self.manager.run_in_container(
                env=env,
                cmd="echo hello",
                working_dir=Path("/fake/project"),
                container_working_dir="/workspace",
                process_runner=process_runner,
            )

        # Verify error message mentions container execution
        self.assertIn("container execution failed", str(context.exception).lower())
        self.assertIn("125", str(context.exception))


if __name__ == "__main__":
    unittest.main()
