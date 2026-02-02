"""Unit tests for environment definition tracking."""

import unittest
from pathlib import Path

from helpers.logging import logger_stub
from tasktree.executor import Executor
from tasktree.hasher import hash_environment_definition
from tasktree.parser import Environment, Recipe, Task
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager, TaskState


class TestHashEnvironmentDefinition(unittest.TestCase):
    """
    Test environment definition hashing.
    @athena: fbb73ccc237c
    """

    def test_hash_environment_definition_deterministic(self):
        """
        Test that hashing same environment twice produces same hash.
        @athena: 37a4cfe4b1a0
        """

        env = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
            preamble="set -e",
        )

        hash1 = hash_environment_definition(env)
        hash2 = hash_environment_definition(env)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # 16-character hash

    def test_hash_environment_definition_shell_change(self):
        """
        Test that changing shell produces different hash.
        @athena: a8fdcd0bd181
        """

        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
        )
        env2 = Environment(
            name="test",
            shell="/bin/zsh",
            args=["-c"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_args_change(self):
        """
        Test that changing args produces different hash.
        @athena: e15d7b6812ba
        """

        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
        )
        env2 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-e", "-c"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_preamble_change(self):
        """
        Test that changing preamble produces different hash.
        @athena: e59fe9e22990
        """

        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
            preamble="",
        )
        env2 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
            preamble="set -e",
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_docker_fields(self):
        """
        Test that changing Docker fields produces different hash.
        @athena: 52d0d07aedf0
        """

        env1 = Environment(
            name="test",
            dockerfile="Dockerfile",
            context=".",
        )
        env2 = Environment(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            volumes=["./src:/app/src"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_environment_definition_args_order_independent(self):
        """
        Test that args order doesn't matter (they're sorted).
        @athena: 2327b764e6b0
        """

        env1 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-e", "-c"],
        )
        env2 = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c", "-e"],
        )

        hash1 = hash_environment_definition(env1)
        hash2 = hash_environment_definition(env2)

        self.assertEqual(hash1, hash2)


class TestCheckEnvironmentChanged(unittest.TestCase):
    """
    Test environment change detection in executor.
    @athena: e7202cf8d971
    """

    def setUp(self):
        """
        Set up test environment.
        @athena: f157d4dcbdad
        """
        self.project_root = Path("/tmp/test")
        self.env = Environment(
            name="test",
            shell="/bin/bash",
            args=["-c"],
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            environments={"test": self.env},
        )
        self.state_manager = StateManager(self.project_root)

        self.executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

    def test_check_environment_changed_no_env(self):
        """
        Test that platform default (no env) returns False.
        @athena: 56d8c158de7d
        """

        task = Task(name="test", cmd="echo test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_environment_changed(
            task, cached_state, "", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertFalse(result)

    def test_check_environment_changed_first_run(self):
        """
        Test that missing cached hash returns True.
        @athena: a4f11f0f5f39
        """

        task = Task(name="test", cmd="echo test", env="test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_environment_changed(
            task, cached_state, "test", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertTrue(result)

    def test_check_environment_changed_unchanged(self):
        """
        Test that matching hash returns False.
        @athena: 218c97f22523
        """
        task = Task(name="test", cmd="echo test", env="test")

        # Compute hash and store in cached state
        env_hash = hash_environment_definition(self.env)
        cached_state = TaskState(
            last_run=123.0, input_state={"_env_hash_test": env_hash}
        )

        result = self.executor._check_environment_changed(
            task, cached_state, "test", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertFalse(result)

    def test_check_environment_changed_shell_modified(self):
        """
        Test that modified shell is detected.
        @athena: a2b621275515
        """
        task = Task(name="test", cmd="echo test", env="test")

        # Store old hash
        old_env = Environment(name="test", shell="/bin/bash", args=["-c"])
        old_hash = hash_environment_definition(old_env)
        cached_state = TaskState(
            last_run=123.0, input_state={"_env_hash_test": old_hash}
        )

        # Recipe now has modified environment
        # (self.env has same shell, but let's modify the recipe)
        self.recipe.environments["test"] = Environment(
            name="test", shell="/bin/zsh", args=["-c"]
        )

        result = self.executor._check_environment_changed(
            task, cached_state, "test", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertTrue(result)

    def test_check_environment_changed_deleted_env(self):
        """
        Test that deleted environment returns True.
        @athena: 1ee2b820e19f
        """

        task = Task(name="test", cmd="echo test", env="test")
        cached_state = TaskState(
            last_run=123.0, input_state={"_env_hash_test": "somehash"}
        )

        # Delete environment from recipe
        self.recipe.environments = {}

        result = self.executor._check_environment_changed(
            task, cached_state, "test", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertTrue(result)


class TestCheckDockerImageChanged(unittest.TestCase):
    """
    Test Docker image ID change detection in executor.
    @athena: e1e6afc3d943
    """

    def setUp(self):
        """
        Set up test environment.
        @athena: c2d62daebe7d
        """

        self.project_root = Path("/tmp/test")

        # Create Docker environment
        self.env = Environment(
            name="builder",
            dockerfile="Dockerfile",
            context=".",
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            environments={"builder": self.env},
        )
        self.state_manager = StateManager(self.project_root)
        self.executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

    def test_check_docker_image_changed_no_cached_id(self):
        """
        Test that missing cached image ID returns True (first run).
        @athena: b0f9b4e70a6f
        """

        # TODO why is this not used?
        # task = Task(name="test", cmd="echo test", env="builder")

        # Cached state has env hash but no image ID (old state file)
        from tasktree.hasher import hash_environment_definition

        env_hash = hash_environment_definition(self.env)
        cached_state = TaskState(
            last_run=123.0, input_state={"_env_hash_builder": env_hash}
        )

        # Mock docker manager to return image ID
        from unittest.mock import Mock

        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-env-builder", "sha256:abc123")
        )

        result = self.executor._check_docker_image_changed(
            self.env, cached_state, "builder", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertTrue(result)

    def test_check_docker_image_changed_same_id(self):
        """
        Test that matching image ID returns False.
        @athena: e141f18876b2
        """

        # TODO why is this not used?
        #  task = Task(name="test", cmd="echo test", env="builder")

        # Cached state with image ID
        image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0, input_state={"_docker_image_id_builder": image_id}
        )

        # Mock docker manager to return same image ID
        from unittest.mock import Mock

        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-env-builder", image_id)
        )

        result = self.executor._check_docker_image_changed(
            self.env, cached_state, "builder", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertFalse(result)

    def test_check_docker_image_changed_different_id(self):
        """
        Test that different image ID returns True (unpinned base updated).
        @athena: 997fd2e71a45
        """

        # TODO why is this not used?
        # task = Task(name="test", cmd="echo test", env="builder")

        # Cached state with old image ID
        old_image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0, input_state={"_docker_image_id_builder": old_image_id}
        )

        # Mock docker manager to return new image ID (base image updated)
        from unittest.mock import Mock

        new_image_id = "sha256:def456"
        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-env-builder", new_image_id)
        )

        result = self.executor._check_docker_image_changed(
            self.env, cached_state, "builder", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )

        self.assertTrue(result)

    def test_check_environment_changed_docker_yaml_and_image(self):
        """
        Test that Docker environment checks both YAML hash and image ID.
        @athena: fccc97ebb3ab
        """

        task = Task(name="test", cmd="echo test", env="builder")

        # Cached state with matching env hash AND matching image ID
        from tasktree.hasher import hash_environment_definition

        env_hash = hash_environment_definition(self.env)
        image_id = "sha256:abc123"
        cached_state = TaskState(
            last_run=123.0,
            input_state={
                "_env_hash_builder": env_hash,
                "_docker_image_id_builder": image_id,
            },
        )

        # Mock docker manager to return same image ID
        from unittest.mock import Mock

        self.executor.docker_manager.ensure_image_built = Mock(
            return_value=("tt-env-builder", image_id)
        )

        # Should return False (both YAML and image ID unchanged)
        result = self.executor._check_environment_changed(
            task, cached_state, "builder", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )
        self.assertFalse(result)

    def test_check_environment_changed_docker_yaml_changed(self):
        """
        Test that YAML change detected without checking image ID.
        @athena: f3ea6140643e
        """

        task = Task(name="test", cmd="echo test", env="builder")

        # Cached state with OLD env hash (YAML changed)
        old_env = Environment(name="builder", dockerfile="OldDockerfile", context=".")
        from tasktree.hasher import hash_environment_definition

        old_env_hash = hash_environment_definition(old_env)

        cached_state = TaskState(
            last_run=123.0,
            input_state={
                "_env_hash_builder": old_env_hash,
                "_docker_image_id_builder": "sha256:abc123",
            },
        )

        # Mock should NOT be called (YAML change detected early)
        from unittest.mock import Mock

        self.executor.docker_manager.ensure_image_built = Mock()

        # Should return True (YAML changed)
        result = self.executor._check_environment_changed(
            task, cached_state, "builder", make_process_runner(TaskOutputTypes.ALL, logger_stub)
        )
        self.assertTrue(result)

        # Verify docker manager was NOT called (early exit on YAML change)
        self.executor.docker_manager.ensure_image_built.assert_not_called()


if __name__ == "__main__":
    unittest.main()
