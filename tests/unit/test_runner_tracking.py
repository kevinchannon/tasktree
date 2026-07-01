"""Unit tests for runner definition tracking."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from helpers.logging import logger_stub
import tasktree.docker as docker_module
from tasktree.executor import Executor
from tasktree.hasher import hash_runner_definition
from tasktree.parser import DockerArgs, DockerRunner, Runner, Recipe, Task
from tasktree.interpreter import Interpreter
from tasktree.process_runner import TaskOutputTypes, make_process_runner
from tasktree.state import StateManager, TaskState


class TestHashRunnerDefinition(unittest.TestCase):
    """
    Test runner definition hashing.
    """

    def test_hash_runner_definition_deterministic(self):
        """
        Test that hashing same runner twice produces same hash.
        """

        runner = Runner(
            name="test",
            interpreter=Interpreter(cmd="bash", preamble="set -e"),
        )

        hash1 = hash_runner_definition(runner)
        hash2 = hash_runner_definition(runner)

        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)  # 16-character hash

    def test_hash_runner_definition_shell_change(self):
        """
        Test that changing shell produces different hash.
        """

        runner1 = Runner(
            name="test",
            interpreter=Interpreter(cmd="bash"),
        )
        runner2 = Runner(
            name="test",
            interpreter=Interpreter(cmd="zsh"),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_args_change(self):
        """
        Test that changing docker run args produces different hash.
        """

        runner1 = DockerRunner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--rm"]),
        )
        runner2 = DockerRunner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--rm", "--network=host"]),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_preamble_change(self):
        """
        Test that changing preamble produces different hash.
        """

        runner1 = Runner(
            name="test",
            interpreter=Interpreter(cmd="bash", preamble=""),
        )
        runner2 = Runner(
            name="test",
            interpreter=Interpreter(cmd="bash", preamble="set -e"),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_docker_fields(self):
        """
        Test that changing Docker fields produces different hash.
        """

        runner1 = DockerRunner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
        )
        runner2 = DockerRunner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            volumes=["./src:/app/src"],
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_type_and_engine_change(self):
        """
        Test that changing type/engine produces a different hash, so cache
        entries are invalidated if a runner's classification changes.
        """

        runner1 = Runner(
            name="test",
            type="containerised",
            engine="docker",
            dockerfile="Dockerfile",
            context=".",
        )
        runner2 = Runner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertNotEqual(hash1, hash2)

    def test_hash_runner_definition_args_order_independent(self):
        """
        Test that docker run args order doesn't matter (they're sorted in hash).
        """

        runner1 = DockerRunner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--rm", "--network=host"]),
        )
        runner2 = DockerRunner(
            name="test",
            dockerfile="Dockerfile",
            context=".",
            args=DockerArgs(run=["--network=host", "--rm"]),
        )

        hash1 = hash_runner_definition(runner1)
        hash2 = hash_runner_definition(runner2)

        self.assertEqual(hash1, hash2)


class TestCheckRunnerChanged(unittest.TestCase):
    """
    Test runner change detection in executor.
    """

    def setUp(self):
        """
        Set up test runner.
        """
        self.project_root = Path("/tmp/test")
        self.runner = Runner(
            name="test",
            interpreter=Interpreter(cmd="bash"),
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            runners={"test": self.runner},
        )
        self.state_manager = StateManager(self.project_root)

        self.executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

    def test_check_runner_changed_no_runner(self):
        """
        Test that platform default (no runner) returns False.
        """

        task = Task(name="test", cmd="echo test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertFalse(result)

    def test_check_runner_changed_first_run(self):
        """
        Test that missing cached hash returns True.
        """

        task = Task(name="test", cmd="echo test", run_in="test")
        cached_state = TaskState(last_run=123.0, input_state={})

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_runner_changed_unchanged(self):
        """
        Test that matching hash returns False.
        """
        task = Task(name="test", cmd="echo test", run_in="test")

        # Compute hash and store in cached state
        runner_hash = hash_runner_definition(self.runner)
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_test": runner_hash}
        )

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertFalse(result)

    def test_check_runner_changed_shell_modified(self):
        """
        Test that modified shell is detected.
        """
        task = Task(name="test", cmd="echo test", run_in="test")

        # Store old hash
        old_runner = Runner(name="test", interpreter=Interpreter(cmd="bash"))
        old_hash = hash_runner_definition(old_runner)
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_test": old_hash}
        )

        # Recipe now has modified runner
        self.recipe.runners["test"] = Runner(name="test", interpreter=Interpreter(cmd="zsh"))

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)

    def test_check_runner_changed_deleted_runner(self):
        """
        Test that deleted runner returns True.
        """

        task = Task(name="test", cmd="echo test", run_in="test")
        cached_state = TaskState(
            last_run=123.0, input_state={"_runner_hash_test": "somehash"}
        )

        # Delete runner from recipe
        self.recipe.runners = {}

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "test",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )

        self.assertTrue(result)


class TestCheckRunnerChangedDocker(unittest.TestCase):
    """
    Test Docker runner change detection in executor (YAML hash, context files,
    and base-image digests; the built image ID is intentionally not used).
    """

    def setUp(self):
        """
        Set up test runner.
        """

        self.project_root = Path("/tmp/test")

        # Create Docker runner
        self.runner = DockerRunner(
            name="builder",
            dockerfile="Dockerfile",
            context=".",
        )
        self.recipe = Recipe(
            tasks={},
            project_root=self.project_root,
            recipe_path=self.project_root / "tasktree.yaml",
            runners={"builder": self.runner},
        )
        self.state_manager = StateManager(self.project_root)
        self.executor = Executor(
            self.recipe, self.state_manager, logger_stub, make_process_runner
        )

    def test_check_runner_changed_docker_all_unchanged(self):
        """
        Test that a Docker runner is unchanged when YAML hash, context, and
        base-image digests all match (the built image ID is deliberately ignored
        because it is non-deterministic under BuildKit).
        """

        task = Task(name="test", cmd="echo test", run_in="builder")

        # Cached state with matching runner hash; no context/base-image entries,
        # so context and digest checks both report "unchanged".
        runner_hash = hash_runner_definition(self.runner)
        cached_state = TaskState(
            last_run=123.0,
            input_state={"_runner_hash_builder": runner_hash},
        )

        # ensure_image_built must NOT be consulted for change detection any more.
        self.executor.docker_manager.ensure_image_built = Mock()

        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )
        self.assertFalse(result)
        self.executor.docker_manager.ensure_image_built.assert_not_called()

    def test_check_runner_changed_docker_yaml_changed(self):
        """
        Test that a YAML change is detected from the runner hash alone.
        """

        task = Task(name="test", cmd="echo test", run_in="builder")

        # Cached state with OLD runner hash (YAML changed)
        old_runner = DockerRunner(name="builder", dockerfile="OldDockerfile", context=".")
        old_runner_hash = hash_runner_definition(old_runner)

        cached_state = TaskState(
            last_run=123.0,
            input_state={"_runner_hash_builder": old_runner_hash},
        )

        # Mock should NOT be called (YAML change detected early)
        self.executor.docker_manager.ensure_image_built = Mock()

        # Should return True (YAML changed)
        result = self.executor._check_runner_changed(
            task,
            cached_state,
            "builder",
            make_process_runner(TaskOutputTypes.ALL, logger_stub),
        )
        self.assertTrue(result)

        # Verify docker manager was NOT called (early exit on YAML change)
        self.executor.docker_manager.ensure_image_built.assert_not_called()


if __name__ == "__main__":
    unittest.main()
