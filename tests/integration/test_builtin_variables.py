"""Integration tests for built-in variables feature."""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tasktree.executor import Executor
from tasktree.parser import parse_recipe
from tasktree.state import StateManager


class TestBuiltinVariables(unittest.TestCase):
    """Test built-in variable substitution in task execution."""

    def setUp(self):
        """Create temporary directory for test recipes."""
        self.test_dir = tempfile.mkdtemp()
        self.recipe_file = Path(self.test_dir) / "tasktree.yaml"

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_all_builtin_variables_in_command(self):
        """Test that all 8 built-in variables work in task commands."""
        # Create output file path
        output_file = Path(self.test_dir) / "output.txt"

        # Create recipe that uses all built-in variables
        recipe_content = f"""
tasks:
  test-vars:
    cmd: |
      echo "project_root={{{{ tt.project_root }}}}" > {output_file}
      echo "recipe_dir={{{{ tt.recipe_dir }}}}" >> {output_file}
      echo "task_name={{{{ tt.task_name }}}}" >> {output_file}
      echo "working_dir={{{{ tt.working_dir }}}}" >> {output_file}
      echo "timestamp={{{{ tt.timestamp }}}}" >> {output_file}
      echo "timestamp_unix={{{{ tt.timestamp_unix }}}}" >> {output_file}
      echo "user_home={{{{ tt.user_home }}}}" >> {output_file}
      echo "user_name={{{{ tt.user_name }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        # Parse recipe and execute task
        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-vars")

        # Read output and verify
        output = output_file.read_text()
        lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output.strip().split("\n")}

        # Verify all variables were substituted
        self.assertIn("project_root", lines)
        self.assertEqual(lines["project_root"], str(recipe.project_root.resolve()))

        self.assertIn("recipe_dir", lines)
        self.assertEqual(lines["recipe_dir"], str(self.recipe_file.parent.resolve()))

        self.assertIn("task_name", lines)
        self.assertEqual(lines["task_name"], "test-vars")

        self.assertIn("working_dir", lines)
        self.assertEqual(lines["working_dir"], str(recipe.project_root.resolve()))

        self.assertIn("timestamp", lines)
        # Verify ISO8601 format
        self.assertRegex(lines["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

        self.assertIn("timestamp_unix", lines)
        # Verify Unix timestamp is numeric
        self.assertTrue(lines["timestamp_unix"].isdigit())

        self.assertIn("user_home", lines)
        # Verify it's a valid directory path
        self.assertTrue(Path(lines["user_home"]).is_absolute())

        self.assertIn("user_name", lines)
        # Verify we got some username (could be from os.getlogin() or env var)
        self.assertTrue(len(lines["user_name"]) > 0)

    def test_timestamp_consistency_within_task(self):
        """Test that timestamp is consistent throughout a single task execution."""
        output_file = Path(self.test_dir) / "timestamps.txt"

        recipe_content = f"""
tasks:
  test-timestamp:
    cmd: |
      echo "{{{{ tt.timestamp }}}}" > {output_file}
      sleep 0.1
      echo "{{{{ tt.timestamp }}}}" >> {output_file}
      echo "{{{{ tt.timestamp_unix }}}}" >> {output_file}
      sleep 0.1
      echo "{{{{ tt.timestamp_unix }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-timestamp")

        output = output_file.read_text()
        lines = output.strip().split("\n")

        # All timestamps should be identical
        self.assertEqual(lines[0], lines[1], "ISO timestamps should be consistent")
        self.assertEqual(lines[2], lines[3], "Unix timestamps should be consistent")

    def test_builtin_vars_with_working_dir(self):
        """Test that tt.working_dir reflects the task's working_dir setting."""
        # Create subdirectory
        subdir = Path(self.test_dir) / "subdir"
        subdir.mkdir()
        output_file = Path(self.test_dir) / "working_dir.txt"

        recipe_content = f"""
tasks:
  test-workdir:
    working_dir: subdir
    cmd: echo "{{{{ tt.working_dir }}}}" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-workdir")

        output = output_file.read_text().strip()
        # Should show the absolute path to subdir
        self.assertEqual(output, str(subdir.resolve()))

    def test_builtin_vars_in_multiline_command(self):
        """Test that built-in variables work in multi-line commands."""
        output_file = Path(self.test_dir) / "multiline.txt"

        recipe_content = f"""
tasks:
  test-multiline:
    cmd: |
      PROJECT={{{{ tt.project_root }}}}
      TASK={{{{ tt.task_name }}}}
      echo "$PROJECT/$TASK" > {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-multiline")

        output = output_file.read_text().strip()
        expected = f"{recipe.project_root.resolve()}/test-multiline"
        self.assertEqual(output, expected)

    def test_recipe_dir_differs_from_project_root_when_recipe_in_subdir(self):
        """Test that recipe_dir points to recipe file location, not project root."""
        # Create recipe in a subdirectory
        recipe_subdir = Path(self.test_dir) / "config"
        recipe_subdir.mkdir()
        recipe_path = recipe_subdir / "tasks.yaml"
        output_file = Path(self.test_dir) / "recipe_dir.txt"

        recipe_content = f"""
tasks:
  test-recipe-dir:
    cmd: |
      echo "project={{{{ tt.project_root }}}}" > {output_file}
      echo "recipe={{{{ tt.recipe_dir }}}}" >> {output_file}
"""
        recipe_path.write_text(recipe_content)

        # Parse with explicit project_root (current directory)
        recipe = parse_recipe(recipe_path, project_root=Path(self.test_dir))
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("test-recipe-dir")

        output = output_file.read_text()
        lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output.strip().split("\n")}

        # project_root should be test_dir
        self.assertEqual(lines["project"], str(Path(self.test_dir).resolve()))
        # recipe_dir should be the subdirectory
        self.assertEqual(lines["recipe"], str(recipe_subdir.resolve()))

    def test_builtin_vars_mixed_with_other_vars(self):
        """Test built-in variables work alongside regular variables and arguments."""
        output_file = Path(self.test_dir) / "mixed.txt"

        recipe_content = f"""
variables:
  server: prod.example.com

tasks:
  deploy:
    args: [region]
    cmd: |
      echo "Deploying from {{{{ tt.project_root }}}}" > {output_file}
      echo "Task: {{{{ tt.task_name }}}}" >> {output_file}
      echo "Server: {{{{ var.server }}}}" >> {output_file}
      echo "Region: {{{{ arg.region }}}}" >> {output_file}
      echo "User: {{{{ tt.user_name }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("deploy", args_dict={"region": "us-west-1"})

        output = output_file.read_text()
        lines = [line for line in output.strip().split("\n")]

        self.assertIn(f"Deploying from {recipe.project_root.resolve()}", lines[0])
        self.assertIn("Task: deploy", lines[1])
        self.assertIn("Server: prod.example.com", lines[2])
        self.assertIn("Region: us-west-1", lines[3])
        # User should be present (from tt.user_name)
        self.assertTrue(lines[4].startswith("User: "))

    def test_builtin_vars_in_working_dir(self):
        """Test that non-circular builtin variables can be used in working_dir."""
        # Create a directory that matches the task name
        task_dir = Path(self.test_dir) / "build-task"
        task_dir.mkdir()
        output_file = Path(self.test_dir) / "result.txt"

        recipe_content = f"""
tasks:
  build-task:
    working_dir: "{{{{ tt.task_name }}}}"
    cmd: |
      echo "task={{{{ tt.task_name }}}}" > {output_file}
      echo "wd={{{{ tt.working_dir }}}}" >> {output_file}
"""
        self.recipe_file.write_text(recipe_content)

        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)
        executor.execute_task("build-task")

        output = output_file.read_text()
        lines = {line.split("=", 1)[0]: line.split("=", 1)[1] for line in output.strip().split("\n")}

        # Verify task_name was substituted in working_dir
        self.assertEqual(lines["task"], "build-task")
        # Verify working_dir reflects the actual resolved path
        self.assertEqual(lines["wd"], str(task_dir.resolve()))

    def test_builtin_vars_in_environment_volumes(self):
        """Test that builtin variables are substituted in environment volume mounts."""
        from unittest.mock import patch, Mock
        import platform

        # Only run on Linux where we can test Docker
        if platform.system() != "Linux":
            self.skipTest("Docker environment tests only run on Linux")

        output_file = Path(self.test_dir) / "docker_test.txt"

        recipe_content = f"""
environments:
  test-env:
    dockerfile: docker/Dockerfile
    context: .
    volumes:
      - "{{{{ tt.project_root }}}}:/workspace"
      - "{{{{ tt.recipe_dir }}}}:/config"
    env_vars:
      PROJECT_PATH: "{{{{ tt.project_root }}}}"
      TASK_NAME_VAR: "{{{{ tt.task_name }}}}"

tasks:
  docker-test:
    env: test-env
    cmd: echo "Testing builtin vars in docker"
"""
        self.recipe_file.write_text(recipe_content)

        # Create docker directory and Dockerfile
        docker_dir = Path(self.test_dir) / "docker"
        docker_dir.mkdir()
        dockerfile = docker_dir / "Dockerfile"
        dockerfile.write_text("FROM alpine:latest\\n")

        # Parse recipe
        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)

        # Mock the docker subprocess calls to capture the command
        docker_run_command = None

        def mock_run(*args, **kwargs):
            nonlocal docker_run_command
            cmd = args[0] if args else kwargs.get('args', [])
            if isinstance(cmd, list) and 'run' in cmd:
                docker_run_command = cmd
            # Mock return values
            if isinstance(cmd, list) and 'inspect' in cmd:
                result = Mock()
                result.stdout = "sha256:test123\\n"
                result.returncode = 0
                return result
            result = Mock()
            result.returncode = 0
            return result

        with patch('tasktree.docker.subprocess.run', side_effect=mock_run):
            # Execute task
            executor.execute_task("docker-test")

        # Verify that volumes were substituted
        self.assertIsNotNone(docker_run_command, "Docker run command should have been captured")

        # Find volume mounts in command
        volume_mounts = []
        for i, arg in enumerate(docker_run_command):
            if arg == "-v" and i + 1 < len(docker_run_command):
                volume_mounts.append(docker_run_command[i + 1])

        # Verify volumes contain absolute paths, not template strings
        self.assertTrue(len(volume_mounts) >= 2, f"Expected at least 2 volume mounts, got {len(volume_mounts)}")

        # Check that tt.project_root was substituted
        project_root_str = str(recipe.project_root.resolve())
        self.assertTrue(
            any(project_root_str in vol for vol in volume_mounts),
            f"Expected project root '{project_root_str}' in volumes, got: {volume_mounts}"
        )

        # Verify no literal template strings remain
        for vol in volume_mounts:
            self.assertNotIn("{{ tt.", vol,
                f"Volume mount should not contain template strings: {vol}")

        # Find environment variables in command
        env_vars = {}
        for i, arg in enumerate(docker_run_command):
            if arg == "-e" and i + 1 < len(docker_run_command):
                env_pair = docker_run_command[i + 1]
                if "=" in env_pair:
                    key, value = env_pair.split("=", 1)
                    env_vars[key] = value

        # Verify environment variables were substituted
        self.assertIn("PROJECT_PATH", env_vars, "PROJECT_PATH env var should be present")
        self.assertEqual(env_vars["PROJECT_PATH"], project_root_str,
            "PROJECT_PATH should contain the resolved project root")

        self.assertIn("TASK_NAME_VAR", env_vars, "TASK_NAME_VAR should be present")
        self.assertEqual(env_vars["TASK_NAME_VAR"], "docker-test",
            "TASK_NAME_VAR should contain the task name")

    def test_env_vars_in_environment_fields(self):
        """Test that {{ env.* }} variables are substituted in environment fields."""
        from unittest.mock import patch, Mock
        import platform
        import os

        # Only run on Linux where we can test Docker
        if platform.system() != "Linux":
            self.skipTest("Docker environment tests only run on Linux")

        # Set test environment variable
        os.environ["TEST_MOUNT_PATH"] = "/test/mount"
        os.environ["TEST_ENV_VALUE"] = "test-value"

        try:
            recipe_content = f"""
environments:
  test-env:
    dockerfile: docker/Dockerfile
    context: .
    volumes:
      - "{{{{ env.TEST_MOUNT_PATH }}}}:/workspace"
    env_vars:
      ENV_VAR_VALUE: "{{{{ env.TEST_ENV_VALUE }}}}"

tasks:
  docker-test:
    env: test-env
    cmd: echo "Testing env vars in docker"
"""
            self.recipe_file.write_text(recipe_content)

            # Create docker directory and Dockerfile
            docker_dir = Path(self.test_dir) / "docker"
            docker_dir.mkdir()
            dockerfile = docker_dir / "Dockerfile"
            dockerfile.write_text("FROM alpine:latest\\n")

            # Parse recipe
            recipe = parse_recipe(self.recipe_file)
            state = StateManager(recipe.project_root)
            state.load()
            executor = Executor(recipe, state)

            # Mock the docker subprocess calls to capture the command
            docker_run_command = None

            def mock_run(*args, **kwargs):
                nonlocal docker_run_command
                cmd = args[0] if args else kwargs.get('args', [])
                if isinstance(cmd, list) and 'run' in cmd:
                    docker_run_command = cmd
                # Mock return values
                if isinstance(cmd, list) and 'inspect' in cmd:
                    result = Mock()
                    result.stdout = "sha256:test123\\n"
                    result.returncode = 0
                    return result
                result = Mock()
                result.returncode = 0
                return result

            with patch('tasktree.docker.subprocess.run', side_effect=mock_run):
                # Execute task
                executor.execute_task("docker-test")

            # Verify that volumes were substituted
            self.assertIsNotNone(docker_run_command, "Docker run command should have been captured")

            # Find volume mounts in command
            volume_mounts = []
            for i, arg in enumerate(docker_run_command):
                if arg == "-v" and i + 1 < len(docker_run_command):
                    volume_mounts.append(docker_run_command[i + 1])

            # Verify volumes contain the substituted env var, not template strings
            self.assertTrue(len(volume_mounts) >= 1, f"Expected at least 1 volume mount, got {len(volume_mounts)}")
            self.assertTrue(
                any("/test/mount" in vol for vol in volume_mounts),
                f"Expected '/test/mount' in volumes, got: {volume_mounts}"
            )

            # Verify no literal template strings remain
            for vol in volume_mounts:
                self.assertNotIn("{{ env.", vol,
                    f"Volume mount should not contain template strings: {vol}")

            # Find environment variables in command
            env_vars = {}
            for i, arg in enumerate(docker_run_command):
                if arg == "-e" and i + 1 < len(docker_run_command):
                    env_pair = docker_run_command[i + 1]
                    if "=" in env_pair:
                        key, value = env_pair.split("=", 1)
                        env_vars[key] = value

            # Verify environment variables were substituted
            self.assertIn("ENV_VAR_VALUE", env_vars, "ENV_VAR_VALUE env var should be present")
            self.assertEqual(env_vars["ENV_VAR_VALUE"], "test-value",
                "ENV_VAR_VALUE should contain the substituted environment variable")
        finally:
            # Clean up test environment variables
            os.environ.pop("TEST_MOUNT_PATH", None)
            os.environ.pop("TEST_ENV_VALUE", None)

    def test_var_vars_in_environment_fields(self):
        """Test that {{ var.* }} variables are substituted in environment fields."""
        from unittest.mock import patch, Mock

        recipe_content = f"""
variables:
  mount_path: /var/data
  env_value: config-value

environments:
  test-env:
    dockerfile: docker/Dockerfile
    context: .
    volumes:
      - "{{{{ var.mount_path }}}}:/workspace"
    env_vars:
      VAR_VALUE: "{{{{ var.env_value }}}}"

tasks:
  docker-test:
    env: test-env
    cmd: echo "Testing var substitution in docker"
"""
        self.recipe_file.write_text(recipe_content)

        # Create docker directory and Dockerfile
        docker_dir = Path(self.test_dir) / "docker"
        docker_dir.mkdir()
        dockerfile = docker_dir / "Dockerfile"
        dockerfile.write_text("FROM alpine:latest\\n")

        # Parse recipe
        recipe = parse_recipe(self.recipe_file)
        state = StateManager(recipe.project_root)
        state.load()
        executor = Executor(recipe, state)

        # Mock the docker subprocess calls to capture the command
        docker_run_command = None

        def mock_run(*args, **kwargs):
            nonlocal docker_run_command
            cmd = args[0] if args else kwargs.get('args', [])
            if isinstance(cmd, list) and 'run' in cmd:
                docker_run_command = cmd
            # Mock return values
            if isinstance(cmd, list) and 'inspect' in cmd:
                result = Mock()
                result.stdout = "sha256:test123\\n"
                result.returncode = 0
                return result
            result = Mock()
            result.returncode = 0
            return result

        with patch('tasktree.docker.subprocess.run', side_effect=mock_run):
            # Execute task
            executor.execute_task("docker-test")

        # Verify that volumes were substituted
        self.assertIsNotNone(docker_run_command, "Docker run command should have been captured")

        # Find volume mounts in command
        volume_mounts = []
        for i, arg in enumerate(docker_run_command):
            if arg == "-v" and i + 1 < len(docker_run_command):
                volume_mounts.append(docker_run_command[i + 1])

        # Verify volumes contain the substituted var, not template strings
        self.assertTrue(len(volume_mounts) >= 1, f"Expected at least 1 volume mount, got {len(volume_mounts)}")
        self.assertTrue(
            any("/var/data" in vol for vol in volume_mounts),
            f"Expected '/var/data' in volumes, got: {volume_mounts}"
        )

        # Verify no literal template strings remain
        for vol in volume_mounts:
            self.assertNotIn("{{ var.", vol,
                f"Volume mount should not contain template strings: {vol}")

        # Find environment variables in command
        env_vars = {}
        for i, arg in enumerate(docker_run_command):
            if arg == "-e" and i + 1 < len(docker_run_command):
                env_pair = docker_run_command[i + 1]
                if "=" in env_pair:
                    key, value = env_pair.split("=", 1)
                    env_vars[key] = value

        # Verify environment variables were substituted
        self.assertIn("VAR_VALUE", env_vars, "VAR_VALUE env var should be present")
        self.assertEqual(env_vars["VAR_VALUE"], "config-value",
            "VAR_VALUE should contain the substituted variable")


if __name__ == "__main__":
    unittest.main()
