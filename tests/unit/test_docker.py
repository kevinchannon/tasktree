"""Unit tests for Docker integration."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from helpers.logging import logger_stub
from tasktree.docker import (
    DockerManager,
    is_docker_runner,
    resolve_container_working_dir,
)
from tasktree.interpreter import Interpreter
from tasktree.parser import DockerArgs, DockerRunner, Runner
from tasktree.process_runner import TaskOutputTypes, make_process_runner


class TestIsDockerRunner(unittest.TestCase):
    """
    Test Docker environment detection.
    """

    def test_docker_runner(self):
        """
        Test runner with dockerfile.
        """
        runner = Runner(
            name="builder",
            type="containerised",
            engine="docker",
            dockerfile="./Dockerfile",
            context=".",
        )
        self.assertTrue(is_docker_runner(runner))

    def test_shell_runner(self):
        """
        Test runner without dockerfile.
        """
        runner = Runner(
            name="bash",
            interpreter=Interpreter(cmd="bash -c"),
        )
        self.assertFalse(is_docker_runner(runner))

    def test_shell_runner_with_explicit_cmd(self):
        """
        Test that shell runners work with explicit cmd list in ShellConfig.
        """
        runner = Runner(
            name="bash",
            interpreter=Interpreter(cmd="bash -c -e"),
        )

        # Verify it's recognized as a shell runner (not Docker)
        self.assertFalse(is_docker_runner(runner))
        self.assertEqual(runner.interpreter.cmd, "bash -c -e")

    def test_docker_runner_with_build_args(self):
        """
        Test that Docker runners use DockerArgs for build arguments.
        """
        runner = Runner(
            name="builder",
            type="containerised",
            engine="docker",
            dockerfile="./Dockerfile",
            context=".",
            args=DockerArgs(build=["--build-arg", "BUILD_VERSION=1.0.0"]),
        )

        # Verify it's recognized as a Docker runner
        self.assertTrue(is_docker_runner(runner))
        self.assertEqual(runner.args.build, ["--build-arg", "BUILD_VERSION=1.0.0"])


class TestResolveContainerWorkingDir(unittest.TestCase):
    """
    Test container working directory resolution.
    """

    def test_both_specified(self):
        """
        Test with both env and task working dirs.
        """
        result = resolve_container_working_dir("/workspace", "src")
        self.assertEqual(result, "/workspace/src")

    def test_only_env_specified(self):
        """
        Test with only env working dir.
        """
        result = resolve_container_working_dir("/workspace", "")
        self.assertEqual(result, "/workspace")

    def test_only_task_specified(self):
        """
        Test with only task working dir.
        """
        result = resolve_container_working_dir("", "src")
        self.assertEqual(result, "/src")

    def test_neither_specified(self):
        """
        Test with neither specified - should return None to use Dockerfile WORKDIR.
        """
        result = resolve_container_working_dir("", "")
        self.assertIsNone(result)

    def test_path_normalization(self):
        """
        Test that paths are normalized.
        """
        result = resolve_container_working_dir("/workspace/", "/src/")
        # Trailing slashes are handled, result has trailing slash from task dir
        self.assertEqual(result, "/workspace/src/")


class TestDockerManager(unittest.TestCase):
    """
    Test DockerManager class.
    """

    def setUp(self):
        """
        Set up test environment.
        """
        self.project_root = Path("/fake/project")
        self.manager = DockerManager(self.project_root, logger_stub)

    @patch("tasktree.docker.subprocess.run")
    def test_ensure_image_built_caching(self, mock_run):
        """
        Test that images are cached per invocation.
        """
        env = DockerRunner(
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
        """
        env = DockerRunner(
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
        Test that docker build command passes args.build list to docker build.
        """
        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args=DockerArgs(build=["--no-cache", "-q"]),
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

        # Verify build args are included verbatim
        self.assertIn("--no-cache", build_call_args)
        self.assertIn("-q", build_call_args)

    @patch("tasktree.docker.subprocess.run")
    def test_build_command_with_empty_build_args(self, mock_run):
        """
        Test that docker build command works with empty build args.
        """
        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            args=DockerArgs(),
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

        # Verify NO extra flags are included (just the base structure)
        self.assertNotIn("--no-cache", build_call_args)
        self.assertNotIn("-q", build_call_args)

    def test_resolve_volume_mount_relative(self):
        """
        Test relative volume path resolution.
        """
        volume = "./src:/workspace/src"
        resolved = self.manager._resolve_volume_mount(volume)
        expected = f"{self.project_root / 'src'}:/workspace/src"
        self.assertEqual(resolved, expected)

    def test_resolve_volume_mount_absolute(self):
        """
        Test absolute volume path resolution.
        """
        volume = "/absolute/path:/container/path"
        resolved = self.manager._resolve_volume_mount(volume)
        self.assertEqual(resolved, "/absolute/path:/container/path")

    @patch("tasktree.docker.os.path.expanduser")
    def test_resolve_volume_mount_home(self, mock_expanduser):
        """
        Test home directory expansion in volume paths.
        """
        mock_expanduser.return_value = "/home/user/.cargo"
        volume = "~/.cargo:/root/.cargo"
        resolved = self.manager._resolve_volume_mount(volume)
        self.assertEqual(resolved, "/home/user/.cargo:/root/.cargo")

    def test_resolve_volume_mount_invalid(self):
        """
        Test invalid volume specification.
        """
        with self.assertRaises(ValueError):
            self.manager._resolve_volume_mount("invalid-no-colon")

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_linux(self, mock_platform):
        """
        Test that user flag is added on Linux.
        """
        mock_platform.return_value = "Linux"
        self.assertTrue(self.manager._should_add_user_flag())

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_darwin(self, mock_platform):
        """
        Test that user flag is added on macOS.
        """
        mock_platform.return_value = "Darwin"
        self.assertTrue(self.manager._should_add_user_flag())

    @patch("tasktree.docker.platform.system")
    def test_should_add_user_flag_windows(self, mock_platform):
        """
        Test that user flag is NOT added on Windows.
        """
        mock_platform.return_value = "Windows"
        self.assertFalse(self.manager._should_add_user_flag())

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid", create=True)
    @patch("tasktree.docker.os.getgid", create=True)
    def test_run_in_container_adds_user_flag_by_default(
        self, mock_getgid, mock_getuid, mock_platform, mock_run
    ):
        """
        Test that --user flag is added by default on Linux.
        """
        mock_platform.return_value = "Linux"
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Find the docker run call (should be the 4th call: docker --version, build, inspect, run)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is present
        self.assertIn("--user", run_call_args)
        user_flag_index = run_call_args.index("--user")
        self.assertEqual(run_call_args[user_flag_index + 1], "1000:1000")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_mounts_project_root_at_its_own_path(
        self, mock_platform, mock_run
    ):
        """
        Test that the project root is bind-mounted read-write at its own host path,
        so the task runs against the real repo without any user-declared volumes.
        """
        mock_platform.return_value = "Windows"  # Skip user flag for simplicity

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
        )

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
            interpreter=Interpreter(cmd="sh"),
        )

        run_call_args = mock_run.call_args_list[3][0][0]

        # The project root must be mounted at the identical path, read-write
        # (no :ro suffix). Use resolve() to match the implementation which
        # resolves the path (adds drive letter on Windows).
        resolved = self.project_root.resolve()
        expected_mount = f"{resolved}:{resolved}"
        self.assertIn(expected_mount, run_call_args)

    @patch("tasktree.docker.subprocess.run")
    def test_image_content_fingerprint_uses_rootfs_layers(self, mock_run):
        """
        image_content_fingerprint returns the image's RootFS layer digests
        (content-addressed), inspected via the RootFS.Layers format.
        """
        mock_run.return_value = Mock(
            stdout='["sha256:aaa","sha256:bbb"]\n'
        )

        fp = self.manager.image_content_fingerprint("tt-env-builder")

        self.assertEqual(fp, '["sha256:aaa","sha256:bbb"]')
        inspect_cmd = mock_run.call_args[0][0]
        self.assertEqual(inspect_cmd[:2], ["docker", "inspect"])
        self.assertIn("{{json .RootFS.Layers}}", inspect_cmd)
        self.assertIn("tt-env-builder", inspect_cmd)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_capture_in_container_returns_stdout_and_runs_argv(
        self, mock_platform, mock_run
    ):
        """
        capture_in_container runs the given argv in the container (with the shared
        run flags + image) and returns its captured stdout.
        """
        mock_platform.return_value = "Windows"  # skip user flag for simplicity

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
        )

        # Isolate the capture command from the build path.
        self.manager.ensure_image_built = Mock(
            return_value=("tt-env-builder", "sha256:abc")
        )
        mock_run.return_value = Mock(stdout="pat\tfile.txt\t123\n")

        process_runner = make_process_runner(TaskOutputTypes.ALL, logger_stub)
        out = self.manager.capture_in_container(
            env, ["sh", "-c", "the-script", "sh", "/base", "*.txt"], process_runner
        )

        self.assertEqual(out, "pat\tfile.txt\t123\n")

        docker_cmd = mock_run.call_args[0][0]
        self.assertEqual(docker_cmd[:3], ["docker", "run", "--rm"])
        self.assertIn("tt-env-builder", docker_cmd)
        # The argv is appended after the image tag.
        image_index = docker_cmd.index("tt-env-builder")
        self.assertEqual(
            docker_cmd[image_index + 1:],
            ["sh", "-c", "the-script", "sh", "/base", "*.txt"],
        )

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_does_not_duplicate_project_root_mount(
        self, mock_platform, mock_run
    ):
        """
        When the user already maps the project root themselves, the auto same-path
        mount is suppressed so the project root is not bind-mounted twice.
        """
        mock_platform.return_value = "Windows"  # Skip user flag for simplicity

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
            # User maps the project root at its own path explicitly.
            volumes=[f"{self.project_root}:{self.project_root}"],
        )

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
            interpreter=Interpreter(cmd="sh"),
        )

        run_call_args = mock_run.call_args_list[3][0][0]

        # The project-root mount appears exactly once (from the user's volume).
        root_mount = f"{self.project_root}:{self.project_root}"
        self.assertEqual(
            run_call_args.count(root_mount),
            1,
            "Project root must not be mounted twice",
        )

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_mounts_temp_script(self, mock_platform, mock_run):
        """
        Test that temp script is mounted into container.
        """
        mock_platform.return_value = "Windows"  # Skip user flag for simplicity

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
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
            interpreter=Interpreter(cmd="sh"),
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
                # The 'sh' interpreter has no ext, so the script has no extension.
                if ":/tmp/tt-script-" in mount and mount.endswith(":ro"):
                    found_script_mount = True
                    break

        self.assertTrue(found_script_mount, "Temp script mount not found in docker command")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_executes_script_not_dash_c(self, mock_platform, mock_run):
        """
        Test that docker container executes script file instead of -c command.
        """
        mock_platform.return_value = "Windows"

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="bash -c"),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify -c flag is NOT present
        self.assertNotIn("-c", run_call_args)

        # Verify script path is present as the last argument. The 'sh' interpreter
        # has no ext, so the script has no extension.
        last_arg = run_call_args[-1]
        self.assertTrue(last_arg.startswith("/tmp/tt-script-"), f"Expected script path to start with /tmp/tt-script-, got {last_arg}")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_skips_user_flag_on_windows(self, mock_platform, mock_run):
        """
        Test that --user flag is NOT added on Windows.
        """
        mock_platform.return_value = "Windows"

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is NOT present
        self.assertNotIn("--user", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid", create=True)
    @patch("tasktree.docker.os.getgid", create=True)
    def test_run_in_container_respects_run_as_root_flag(
        self, mock_getgid, mock_getuid, mock_platform, mock_run
    ):
        """
        Test that run_as_root=True prevents --user flag from being added.
        """
        mock_platform.return_value = "Linux"
        mock_getuid.return_value = 1000
        mock_getgid.return_value = 1000

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify --user flag is NOT present when run_as_root=True
        self.assertNotIn("--user", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    def test_run_in_container_includes_run_args(self, mock_platform, mock_run):
        """
        Test that args.run are properly included in docker run command.
        """
        mock_platform.return_value = "Windows"  # Skip user flag for simplicity

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
            args=DockerArgs(run=["--memory=512m", "--cpus=1", "--network=host"]),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify run args are included in the command
        self.assertIn("--memory=512m", run_call_args)
        self.assertIn("--cpus=1", run_call_args)
        self.assertIn("--network=host", run_call_args)

        # Verify run args appear before the image tag
        # Command structure: docker run --rm [run_args] [volumes] [ports] [env] [image] [shell] -c [cmd]
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
    def test_run_in_container_with_empty_run_args(self, mock_platform, mock_run):
        """
        Test that empty args.run list works correctly.
        """
        mock_platform.return_value = "Windows"

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Should succeed without errors
        run_call_args = mock_run.call_args_list[3][0][0]

        # Basic command structure should be present
        self.assertEqual(run_call_args[0], "docker")
        self.assertEqual(run_call_args[1], "run")
        self.assertIn("tt-env-builder", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid", create=True, return_value=1000)
    @patch("tasktree.docker.os.getgid", create=True, return_value=1000)
    def test_run_in_container_with_substituted_variables_in_volumes(
        self, mock_getgid, mock_getuid, mock_platform, mock_run
    ):
        """
        Test that volume mounts work correctly after variable substitution.

        Note: Variable substitution happens in the executor before calling docker manager.
        This test verifies that the docker manager correctly handles already-substituted paths.
        """
        mock_platform.return_value = "Linux"

        # Environment with already-substituted path (as would come from executor)
        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="sh -c"),
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
            interpreter=Interpreter(cmd="sh"),
        )

        # Find the docker run call (should be the 4th call)
        run_call_args = mock_run.call_args_list[3][0][0]

        # The user's volume already maps the project root (/fake/project), so the
        # auto same-path mount is suppressed (dedup). Two -v flags remain: the
        # temp script mount and the user-defined volume.
        volume_indices = [i for i, arg in enumerate(run_call_args) if arg == "-v"]
        self.assertEqual(
            2,
            len(volume_indices),
            "Expected 2 volume mounts: script and user-defined (no duplicate root mount)",
        )

        # Verify the user-defined volume mount uses the absolute path correctly
        self.assertIn("/fake/project:/workspace", run_call_args)
        # And the auto same-path mount must NOT have been added.
        self.assertNotIn("/fake/project:/fake/project", run_call_args)

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid", create=True, return_value=1000)
    @patch("tasktree.docker.os.getgid", create=True, return_value=1000)
    def test_run_in_container_with_windows_shell(self, mock_getgid, mock_getuid, mock_platform, mock_run):
        """
        Test that Windows shells (cmd.exe) use appropriate script extension (.bat).
        """
        mock_platform.return_value = "Linux"  # Host platform (doesn't matter for container)

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile.windows",
            context=".",
            interpreter=Interpreter(cmd="cmd.exe /c"),
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
            interpreter=Interpreter(cmd="cmd.exe", ext=".bat"),
        )

        # Find the docker run call
        run_call_args = mock_run.call_args_list[3][0][0]

        # Verify script path ends with .bat (not .sh)
        last_arg = run_call_args[-1]
        self.assertTrue(last_arg.startswith("/tmp/tt-script-"), f"Expected script path to start with /tmp/tt-script-, got {last_arg}")
        self.assertTrue(last_arg.endswith(".bat"), f"Expected script path to end with .bat for cmd.exe, got {last_arg}")

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid", create=True, return_value=1000)
    @patch("tasktree.docker.os.getgid", create=True, return_value=1000)
    def test_run_in_container_with_powershell(self, mock_getgid, mock_getuid, mock_platform, mock_run):
        """
        Test that PowerShell uses .ps1 extension.
        """
        mock_platform.return_value = "Linux"

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile.windows",
            context=".",
            interpreter=Interpreter(cmd="powershell -Command"),
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
            interpreter=Interpreter(cmd="powershell -ExecutionPolicy Bypass -File", ext=".ps1"),
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
        """
        env = DockerRunner(
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
        """
        env = DockerRunner(
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

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="bash -c"),
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
                interpreter=Interpreter(cmd="sh"),
            )

        # Verify error message mentions script creation
        self.assertIn("temporary script", str(context.exception).lower())

    @patch("tasktree.docker.subprocess.run")
    @patch("tasktree.docker.platform.system")
    @patch("tasktree.docker.os.getuid", create=True, return_value=1000)
    @patch("tasktree.docker.os.getgid", create=True, return_value=1000)
    def test_error_on_docker_run_failure(self, mock_getgid, mock_getuid, mock_platform, mock_run):
        """
        Test that DockerError is raised when docker run fails.
        """
        mock_platform.return_value = "Linux"

        env = DockerRunner(
            name="builder",
            dockerfile="./Dockerfile",
            context=".",
            interpreter=Interpreter(cmd="bash -c"),
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
                interpreter=Interpreter(cmd="sh"),
            )

        # Verify error message mentions container execution
        self.assertIn("container execution failed", str(context.exception).lower())
        self.assertIn("125", str(context.exception))


if __name__ == "__main__":
    unittest.main()
